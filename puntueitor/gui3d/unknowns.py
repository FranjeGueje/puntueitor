"""
Rescate de juegos desconocidos en segundo plano, para el carrusel.

El qué se hace vive en `core.services.unknown_actions`, compartido con la
TUI; aquí solo está el cómo hacerlo sin congelar el render. La TUI puede
permitirse bloquear su hilo mientras IGDB contesta —se queda quieta un
momento y ya está—, pero aquí serían varios segundos a cero fotogramas por
segundo con las cajas paradas a media animación.
"""
import logging
import queue
import threading
from dataclasses import dataclass

from puntueitor.core.services.unknown_actions import (
    SearchResult,
    Unknown,
    adopt_result,
    resolve_by_store,
    search_igdb,
)

logger = logging.getLogger(__name__)

#: Cada cuánto comprueba el hilo si le han pedido parar mientras espera
#: trabajo. Igual que en `covers.CoverLoader` y `enrichment.EnrichWorker`.
_WORKER_POLL_TIMEOUT = 0.2

#: Los tres trabajos que sabe hacer.
SEARCH = "search"
ADOPT = "adopt"
STORE = "store"


@dataclass(frozen=True)
class UnknownJob:
    """Qué hay que hacer y sobre qué desconocido."""

    kind: str
    unknown: Unknown
    query: str | None = None          # solo SEARCH
    result: SearchResult | None = None  # solo ADOPT


class UnknownWorker:
    """
    Hace las gestiones lentas de los desconocidos fuera del hilo de render.

    Mismo patrón que `covers.CoverLoader` y `enrichment.EnrichWorker`, y por
    el mismo motivo: hilo PROPIO y `daemon=True`, nunca un
    `ThreadPoolExecutor` — sus hilos no son daemon y `concurrent.futures`
    registra un `atexit` que los espera, así que cerrar la ventana se
    quedaría colgado hasta que IGDB contestara.

    Un solo hilo: son gestiones que se piden a mano, de una en una.

    El hilo solo toca red y SQLite; lo que sea API de Panda3D se hace al
    recoger con `poll()`, ya en el hilo principal.
    """

    def __init__(self, repository):
        self._repository = repository
        self._pending: queue.Queue[UnknownJob] = queue.Queue()
        self._done: queue.Queue[tuple[UnknownJob, object]] = queue.Queue()
        # Solo se toca desde el hilo principal (`request` y `poll`).
        self._inflight: set[tuple[str, str]] = set()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._worker, name="unknown-worker", daemon=True,
        )
        self._thread.start()

    def request(self, job: UnknownJob) -> bool:
        """
        Encola un trabajo. False si ya hay otro en curso para ESE
        desconocido: una búsqueda tarda segundos sin que la interfaz dé
        señal, y volver a pulsar A es lo natural.
        """
        if job.unknown.key in self._inflight:
            return False
        self._inflight.add(job.unknown.key)
        self._pending.put(job)
        return True

    def _run(self, job: UnknownJob):
        """Ninguna de las tres lanza: los errores vienen en el resultado."""
        if job.kind == SEARCH:
            return search_igdb(job.query or job.unknown.title)
        if job.kind == ADOPT:
            return adopt_result(self._repository, job.unknown, job.result)
        return resolve_by_store(self._repository, job.unknown)

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._pending.get(timeout=_WORKER_POLL_TIMEOUT)
            except queue.Empty:
                continue
            if self._stop.is_set():
                # Se ha pedido cerrar mientras esperaba en la cola.
                continue
            self._done.put((job, self._run(job)))

    def poll(self) -> list[tuple[UnknownJob, object]]:
        """Lo terminado desde la última llamada. Va en el hilo principal."""
        results = []
        while True:
            try:
                job, result = self._done.get_nowait()
            except queue.Empty:
                break
            self._inflight.discard(job.unknown.key)
            results.append((job, result))
        return results

    def shutdown(self) -> None:
        """
        Pide al hilo que pare. NO lo espera: es daemon precisamente para que
        cerrar la aplicación sea inmediato aunque haya una búsqueda a medias.

        Una adopción interrumpida no deja el juego a medias: `adopt_result`
        escribe primero la relación en `resolvers` y solo entonces lo quita
        de desconocidos, así que lo peor que puede pasar es que se quede sin
        enriquecer.
        """
        self._stop.set()
