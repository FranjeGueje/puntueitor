"""
Volver a preguntar a las tiendas y meter en la biblioteca lo que falte.

Tercer hermano de `game_actions.py` y `unknown_actions.py`, con el mismo
contrato: nada de Textual ni de Panda3D, los imports pesados dentro de la
función, y los errores se cuentan por el camino en vez de tumbar la operación.

Aquí vive la parte de la recarga de la TUI (`tui/app.py:do_reload`) que no era
suya: montar el servicio de IGDB, el lector de Heroic y los enrichers, llamar
al pipeline y guardar lo que va saliendo. Lo que cada interfaz hace con eso —
barra de estado, filas, cajas del carrusel— se queda en cada interfaz.

Tres operaciones, de menos a más destructiva, las mismas que ofrece la TUI:

* `refresh_library()` (su tecla "r") — **no borra nada**. No se vuelve a pedir
  a IGDB nada ya cacheado, así que una biblioteca resuelta apenas toca la red
  y lo único que se resuelve de verdad son los juegos nuevos.
* `enrich_all()` (su "E") — borra los datos extra (duración, notas) y los
  vuelve a buscar. La biblioteca sigue siendo la misma.
* `regenerate_library()` (su "R") — borra `puntueitor.db` entero y lo
  reconstruye. Cientos de peticiones y minutos.

Las tres son funciones con nombre propio y no una sola con banderas: en el
sitio de la llamada tiene que leerse qué se va a perder.

`force_store_refresh` va aparte de `refresh` porque solo afecta al listado de
propiedad de Steam, y ese hay que volver a pedirlo SIEMPRE: es justamente lo
que hace que aparezcan los juegos comprados desde la última vez.
"""
import logging
from collections.abc import Callable

from puntueitor.core.models import Game, Library
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.services.game_actions import ENRICHED_FIELDS

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


def regenerate_library(
    repo: LibraryRepository,
    *,
    on_game: Callable[[Game], None] | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    on_enriched: Callable[[Game], None] | None = None,
) -> int:
    """
    Tira la base de datos de juegos y la reconstruye entera desde las tiendas.

    Es lo más destructivo que hace la aplicación y por eso es una función con
    nombre propio en vez de un parámetro de `refresh_library`: en el sitio de
    la llamada tiene que leerse qué se va a perder.

    `puntueitor.db` se lleva por delante las relaciones con IGDB
    (`resolvers`), la caché de fichas, los extras **y los desconocidos**. Lo
    único que sobrevive es `library.sqlite` —terminado, oculto, pendiente,
    favorito—, que vive en otro fichero justamente para esto: es lo único
    irrecuperable, porque no está en ninguna API.

    Son cientos de peticiones a IGDB y minutos de espera.
    """
    # Se VACÍAN las tablas en vez de borrar el fichero, que es lo que hacía
    # la TUI. Borrarlo no sirve: los cachers mantienen una conexión abierta
    # por hilo, y con una abierta `unlink` solo quita el nombre — las
    # conexiones siguen sobre el inodo huérfano, así que la base "borrada"
    # sigue contestando y todo lo reconstruido acaba en un fichero fantasma
    # que se pierde al cerrar. Vaciar las tablas sí lo ven todas.
    for cacher in (
        repo.resolvers_cacher, repo.igdb_cacher,
        repo.extras_cacher, repo.unknown_cacher,
    ):
        cacher.clear_tables()

    logger.info("base de datos vaciada, regenerando desde las tiendas")
    return refresh_library(
        repo, refresh=True, force_store_refresh=True,
        on_game=on_game, on_progress=on_progress, on_enriched=on_enriched,
    )


def enrich_all(
    repo: LibraryRepository,
    *,
    on_game: Callable[[Game], None] | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> int:
    """
    Rehace los datos extra de TODA la biblioteca y devuelve cuántos cambiaron.

    Borra la tabla de extras y vuelve a preguntar duración (HowLongToBeat) y
    notas (Steam/SteamDB) juego a juego. Sirve cuando esos datos han quedado
    viejos o mal, que es lo que no arregla un enriquecido normal: ese se salta
    lo que ya tiene valor y lo que ya se buscó sin éxito (`hltb_checked`).

    Los juegos se releen del repositorio DESPUÉS de borrar, y no se usan los
    que tenga en memoria quien llama: esos conservan sus duraciones, y con
    `overwrite=False` el enricher se saltaría justo lo que se acaba de pedir
    rehacer.

    BLOQUEA y tarda: una petición de red por juego. `should_stop` deja
    cortarlo (al cerrar la aplicación); lo ya guardado se queda.

    No toca `resolvers` ni los estados del usuario: la biblioteca sigue siendo
    la misma, solo se rehace lo que se puede volver a pedir.
    """
    from puntueitor.core.enrichers.hltb_enricher import HLTBEnricher
    from puntueitor.core.enrichers.steam_score_enricher import SteamScoreEnricher
    from puntueitor.core.resolvers.hltb_resolver import HLTBResolver

    repo.extras_cacher.clear_all()
    logger.info("extras borrados, volviendo a enriquecer la biblioteca")

    hltb = HLTBEnricher(client=HLTBResolver(), extras_cacher=repo.extras_cacher)
    steam = SteamScoreEnricher(igdb_cacher=repo.igdb_cacher)

    games = list(repo.load())
    total = len(games)
    enriquecidos = 0

    for index, game in enumerate(games, start=1):
        if should_stop is not None and should_stop():
            logger.info(f"enriquecido interrumpido en {index} de {total}")
            break
        if on_progress is not None:
            on_progress(index, total, game.title)

        try:
            enriched = steam.enrich(hltb.enrich(game))
        except Exception as error:  # noqa: BLE001 - un juego no tumba el lote
            logger.warning(f"no se pudo enriquecer {game.title!r}: {error}")
            continue

        if any(getattr(enriched, field) is not None for field in ENRICHED_FIELDS):
            repo.save_game(enriched)
            enriquecidos += 1
            if on_game is not None:
                on_game(enriched)

    logger.info(f"enriquecidos {enriquecidos} de {total} juegos")
    return enriquecidos
