"""
Enriquecido de juegos en segundo plano para el carrusel.

El qué se busca vive en `core.services.game_actions.enrich_game`, compartido
con la TUI; aquí solo está el cómo hacerlo sin congelar el render.
"""
import logging
import queue
import threading

from puntueitor.core.services.game_actions import EnrichResult, enrich_game

logger = logging.getLogger(__name__)

#: Cada cuánto comprueba el hilo si le han pedido parar mientras espera
#: trabajo. El mismo criterio que en `covers.CoverLoader`: corto para que
#: `shutdown()` tenga efecto enseguida.
_WORKER_POLL_TIMEOUT = 0.2


class EnrichWorker:
    """
    Enriquece juegos en segundo plano, de uno en uno.

    Mismo patrón que `covers.CoverLoader` y por el mismo motivo: un hilo
    PROPIO y `daemon=True`, nunca un `ThreadPoolExecutor` — sus hilos son
    no-daemon y `concurrent.futures` registra un `atexit` que los espera, así
    que cerrar la ventana se quedaría colgado hasta que terminara la petición
    en curso (la nota larga está en `CoverLoader`).

    Un solo hilo, no cuatro: esto se pide a mano sobre un juego concreto, no
    en ráfagas de decenas como las carátulas.

    El hilo solo toca la red y SQLite. Todo lo que sea API de Panda3D se hace
    en el hilo principal, al recoger con `poll()`.
    """

    def __init__(self, repository):
        self._repository = repository
        self._pending: queue.Queue[tuple[object, object]] = queue.Queue()
        self._done: queue.Queue[tuple[object, EnrichResult]] = queue.Queue()
        # Solo se toca desde el hilo principal (`request` y `poll`), así que
        # no necesita cerrojo.
        self._inflight: set[object] = set()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._worker, name="enrich-worker", daemon=True,
        )
        self._thread.start()

    def request(self, key: object, game) -> bool:
        """
        Encola el enriquecido de `game`, asociado a `key`.

        Devuelve False si ese juego ya está en la cola o en curso. Importa
        porque enriquecer tarda varios segundos sin que el carrusel dé señal
        de estar haciendo nada, y volver a entrar en el menú y pulsar otra
        vez es lo natural: sin esto se lanzarían dos búsquedas a la vez
        contra el mismo juego.
        """
        if key in self._inflight:
            return False
        self._inflight.add(key)
        self._pending.put((key, game))
        return True

    def _worker(self) -> None:
        """
        Bucle del hilo: coge peticiones y las enriquece.

        La espera lleva timeout en vez de bloquear para siempre para que el
        hilo compruebe `_stop` de vez en cuando y termine solo tras un
        `shutdown()`, sin centinelas que lo despierten.
        """
        while not self._stop.is_set():
            try:
                key, game = self._pending.get(timeout=_WORKER_POLL_TIMEOUT)
            except queue.Empty:
                continue
            if self._stop.is_set():
                # Se ha pedido cerrar mientras esperaba en la cola.
                continue
            # `enrich_game` no lanza: los errores vienen dentro del
            # resultado, así que aquí no hace falta try.
            self._done.put((key, enrich_game(self._repository, game)))

    def poll(self) -> list[tuple[object, EnrichResult]]:
        """
        Lo que ha terminado desde la última llamada. Se llama una vez por
        frame desde el hilo principal.
        """
        results = []
        while True:
            try:
                key, result = self._done.get_nowait()
            except queue.Empty:
                break
            self._inflight.discard(key)
            results.append((key, result))
        return results

    def shutdown(self) -> None:
        """
        Pide al hilo que pare. NO lo espera: es daemon justamente para que
        cerrar la aplicación sea inmediato aunque haya una búsqueda a medias.
        Lo ya guardado en la base de datos se queda; lo que faltara se puede
        volver a pedir.
        """
        self._stop.set()
