"""
Volver a preguntar a las tiendas y meter en la biblioteca lo que falte.

Tercer hermano de `game_actions.py` y `unknown_actions.py`, con el mismo
contrato: nada de Textual ni de Panda3D, los imports pesados dentro de la
función, y los errores se cuentan por el camino en vez de tumbar la operación.

Aquí vive la parte de la recarga de la TUI (`tui/app.py:do_reload`) que no era
suya: montar el servicio de IGDB, el lector de Heroic y los enrichers, llamar
al pipeline y guardar lo que va saliendo. Lo que cada interfaz hace con eso —
barra de estado, filas, cajas del carrusel— se queda en cada interfaz.

Los dos modos, tal como los distingue la TUI:

* **refresh=False** (la de la tecla "r"): no se vuelve a pedir a IGDB nada que
  ya esté cacheado, así que una biblioteca ya resuelta apenas toca la red y lo
  único que se resuelve de verdad son los juegos nuevos. **No borra nada.**
* **refresh=True** (la de "R", "Regenerar TODO"): ignora las cachés y vuelve a
  preguntarlo todo. El borrado de `puntueitor.db` que la acompaña NO está aquí:
  es una decisión destructiva y se queda a la vista, en quien la ofrece.

`force_store_refresh` va aparte de `refresh` porque solo afecta al listado de
propiedad de Steam, y ese hay que volver a pedirlo SIEMPRE: es justamente lo
que hace que aparezcan los juegos comprados desde la última vez.
"""
import logging
from collections.abc import Callable

from puntueitor.core.models import Game, Library
from puntueitor.core.repository.library_repository import LibraryRepository

logger = logging.getLogger(__name__)


def refresh_library(
    repo: LibraryRepository,
    *,
    refresh: bool = False,
    force_store_refresh: bool = True,
    on_game: Callable[[Game], None] | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    on_enriched: Callable[[Game], None] | None = None,
) -> int:
    """
    Recorre las tiendas y devuelve cuántos juegos se cargaron.

    BLOQUEA de lo lindo: consulta la API de Steam, lee Heroic del disco y
    resuelve contra IGDB juego a juego. Va en un hilo en las dos interfaces.

    Los tres callbacks se llaman **desde hilos que no son el de la interfaz**:
    `on_game` y `on_progress` desde el hilo que ejecuta esto, y `on_enriched`
    desde el pool interno del pipeline. Quien los reciba solo puede ENCOLAR;
    tocar la interfaz ahí es un fallo difícil de reproducir.

    Los enrichers van con `overwrite=False` y con los extras ya conocidos
    precargados, así que un juego con su duración ya sabida no vuelve a
    preguntar a HowLongToBeat.
    """
    # Dentro: arrastran red y toda la cadena del pipeline, y este módulo lo
    # importa gente que solo quiere las otras funciones del paquete.
    from puntueitor.core.config import ConfigManager
    from puntueitor.core.enrichers.hltb_enricher import HLTBEnricher
    from puntueitor.core.enrichers.steam_score_enricher import SteamScoreEnricher
    from puntueitor.core.heroics import HeroicsLoader
    from puntueitor.core.igdb.service import IGDBService
    from puntueitor.core.pipeline.load_steam_library import load_library
    from puntueitor.core.resolvers.hltb_resolver import HLTBResolver

    config = ConfigManager().get

    heroic_loader = None
    if config.gog_is_active or config.epic_is_active or config.amazon_is_active:
        heroic_loader = HeroicsLoader()

    enrichers = []
    try:
        enrichers.append(HLTBEnricher(
            client=HLTBResolver(), overwrite=False,
            extras_cacher=repo.extras_cacher,
        ))
    except Exception as error:  # noqa: BLE001 - se sigue sin ese enricher
        logger.warning(f"no se pudo preparar HLTB: {error}")
    try:
        enrichers.append(SteamScoreEnricher(
            overwrite=False, igdb_cacher=repo.igdb_cacher,
        ))
    except Exception as error:  # noqa: BLE001
        logger.warning(f"no se pudo preparar las notas de Steam: {error}")

    extras_cache = repo.extras_cacher.get_all_extras()

    games = load_library(
        engine=IGDBService(),
        heroic_loader=heroic_loader,
        refresh=refresh,
        force_store_refresh=force_store_refresh,
        progress_callback=on_progress,
        enrichers=enrichers or None,
        enrichment_callback=on_enriched if enrichers else None,
        extras_cache=extras_cache or None,
    )

    loaded = []
    for game in games:
        loaded.append(game)
        # Guardado sobre la marcha, no solo al final: una actualización de
        # una biblioteca grande dura minutos, y si se corta a medias lo ya
        # averiguado no se pierde.
        if game.duration_hours is not None:
            repo.save_game(game)
        if on_game is not None:
            on_game(game)

    repo.save(Library.from_iterable(loaded))
    logger.info(f"biblioteca actualizada: {len(loaded)} juegos")
    return len(loaded)
