"""
Actualización de la biblioteca en segundo plano, para el carrusel.

El qué se hace vive en `core.services.library_refresh`, compartido con la TUI;
aquí solo está el cómo hacerlo sin congelar el render. Y aquí importa más que
en ningún otro sitio: esto tarda minutos —pregunta a la API de Steam, lee
Heroic y resuelve contra IGDB juego a juego—, así que hacerlo en el hilo
principal dejaría el carrusel muerto todo ese rato.
"""
import logging
import queue
import threading
from dataclasses import dataclass

from puntueitor.core.services.library_refresh import (
    enrich_all,
    refresh_library,
    regenerate_library,
    update_extras,
)

logger = logging.getLogger(__name__)

#: Cada cuánto comprueba el hilo si le han pedido parar. Igual que en el
#: resto de trabajadores del carrusel.
_WORKER_POLL_TIMEOUT = 0.2

#: Los tres tipos de mensaje. Van todos por la MISMA cola para que lleguen en
#: orden: si el "he terminado" pudiera adelantar al último juego, el carrusel
#: escondería el progreso antes de haber metido la última caja.
PROGRESS = "progress"
GAME = "game"
DONE = "done"

#: Los cuatro trabajos, de menos a más destructivo. Los cuatro mandan los
#: mismos mensajes, así que para el carrusel son lo mismo: juegos que llegan.
SOFT = "soft"
UPDATE_EXTRAS = "update_extras"
ENRICH_ALL = "enrich_all"
REGENERATE = "regenerate"

#: Cómo se llama cada uno mientras trabaja.
MODE_LABELS = {
    SOFT: "Actualizando biblioteca",
    UPDATE_EXTRAS: "Enriqueciendo todo",
    ENRICH_ALL: "Enriqueciendo todo",
    REGENERATE: "Regenerando todo",
}


@dataclass(frozen=True)
class Progress:
    """Por dónde va: `(hecho, total, "[Tienda] Título")`."""

    current: int
    total: int
    name: str


@dataclass(frozen=True)
class Done:
    """Se acabó. `error` va puesto si se cayó a medias."""

    loaded: int = 0
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class RefreshWorker:
    """
    Actualiza la biblioteca en su propio hilo y va contando qué encuentra.

    Mismo patrón que `covers.CoverLoader`, `enrichment.EnrichWorker` y
    `unknowns.UnknownWorker`: hilo PROPIO y `daemon=True`, nunca un
    `ThreadPoolExecutor` —sus hilos no son daemon y su `atexit` los espera, y
    aquí eso significaría no poder cerrar la ventana hasta que terminara una
    actualización de varios minutos—, cola drenada con `poll()` desde la tarea
    por frame, y `shutdown()` que no espera a nadie.

    Solo una actualización a la vez: `start()` devuelve False si ya hay una en
    marcha. Dos a la vez se pisarían escribiendo en las mismas tablas.

    El hilo solo toca red y SQLite. Nada de Panda3D: los juegos salen por la
    cola y es el hilo principal quien construye sus cajas.
    """

    def __init__(self, repository):
        self._repository = repository
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.mode = SOFT

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, mode: str = SOFT) -> bool:
        """
        Lanza uno de los tres trabajos. False si ya había uno en curso: dos a
        la vez se pisarían escribiendo en las mismas tablas.
        """
        if self.running:
            return False
        self.mode = mode
        self._thread = threading.Thread(
            target=self._worker, name="refresh-worker", daemon=True,
        )
        self._thread.start()
        return True

    def _worker(self) -> None:
        """
        Los callbacks de aquí los llaman hilos distintos (el del pipeline y
        su pool de enriquecido), así que lo único que hacen es encolar.
        """
        def on_progress(current: int, total: int, name: str) -> None:
            if not self._stop.is_set():
                self._events.put((PROGRESS, Progress(current, total, name)))

        def on_game(game) -> None:
            if not self._stop.is_set():
                self._events.put((GAME, game))

        try:
            if self.mode == UPDATE_EXTRAS:
                loaded = update_extras(
                    self._repository,
                    on_game=on_game,
                    on_progress=on_progress,
                    should_stop=self._stop.is_set,
                )
            elif self.mode == ENRICH_ALL:
                loaded = enrich_all(
                    self._repository,
                    on_game=on_game,
                    on_progress=on_progress,
                    should_stop=self._stop.is_set,
                )
            elif self.mode == REGENERATE:
                loaded = regenerate_library(
                    self._repository,
                    on_game=on_game,
                    on_progress=on_progress,
                    # Los enriquecidos llegan por el mismo camino que los
                    # juegos: para el carrusel un juego enriquecido es "este
                    # juego, con más datos", y ya sabe si tiene caja o no.
                    on_enriched=on_game,
                )
            else:
                loaded = refresh_library(
                    self._repository,
                    force_store_refresh=True,
                    on_game=on_game,
                    on_progress=on_progress,
                    on_enriched=on_game,
                )
        except Exception as error:  # noqa: BLE001 - se cuenta, no se lanza
            logger.exception("gui3d: la actualización falló")
            self._events.put((DONE, Done(error=error)))
            return

        self._events.put((DONE, Done(loaded=loaded)))

    def poll(self) -> list[tuple[str, object]]:
        """Lo que haya llegado, en orden. Va en el hilo principal."""
        eventos = []
        while True:
            try:
                eventos.append(self._events.get_nowait())
            except queue.Empty:
                break
        return eventos

    def shutdown(self) -> None:
        """
        Pide parar. NO espera: el hilo es daemon justamente para que cerrar
        la ventana sea inmediato aunque queden minutos de actualización.

        Lo ya averiguado no se pierde: `refresh_library` guarda los extras
        sobre la marcha y lo canónico lo escriben los resolvers según
        resuelven.
        """
        self._stop.set()
