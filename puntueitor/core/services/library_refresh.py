"""
Volver a preguntar a las tiendas y meter en la biblioteca lo que falte.

Tercer hermano de `game_actions.py` y `unknown_actions.py`, con el mismo
contrato: nada de Textual ni de Panda3D, los imports pesados dentro de la
función, y los errores se cuentan por el camino en vez de tumbar la operación.

Aquí vive la parte de la recarga de la TUI (`tui/app.py:do_reload`) que no era
suya: montar el servicio de IGDB, los proveedores de tienda y los enrichers, llamar
al pipeline y guardar lo que va saliendo. Lo que cada interfaz hace con eso —
barra de estado, filas, cajas del carrusel— se queda en cada interfaz.

Cuatro operaciones, de menos a más destructiva:

* `refresh_library()` (la tecla "r" de la TUI) — **no borra nada**. No se
  vuelve a pedir a IGDB nada ya cacheado, así que una biblioteca resuelta
  apenas toca la red y lo único que se resuelve de verdad son los juegos
  nuevos.
* `update_extras()` — **tampoco borra nada**. Vuelve a preguntar la duración y
  las notas de todos los juegos y las escribe encima de las que hubiera. Si
  algo no se encuentra o la red falla, se queda el valor viejo.
* `enrich_all()` (su "E") — borra los datos extra (duración, notas) y los
  vuelve a buscar. La biblioteca sigue siendo la misma.
* `regenerate_library()` (su "R") — borra `puntueitor.db` entero y lo
  reconstruye. Cientos de peticiones y minutos.

Las cuatro son funciones con nombre propio y no una sola con banderas: en el
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

    BLOQUEA de lo lindo: consulta la API de cada tienda y
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
    from puntueitor.core.enrichers.factory import build_enrichers
    from puntueitor.core.igdb.service import IGDBService
    from puntueitor.core.pipeline.load_library import load_library

    config = ConfigManager().get

    enrichers = build_enrichers(repo)

    extras_cache = repo.extras_cacher.get_all_extras()

    games = load_library(
        engine=IGDBService(),
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
    from puntueitor.core.enrichers.factory import build_enrichers

    repo.extras_cacher.clear_all()
    logger.info("extras borrados, volviendo a enriquecer la biblioteca")

    # Con la tabla recién vaciada, "hay dato" y "es nuevo" son lo mismo.
    def hubo_datos(game: Game, enriched: Game) -> bool:
        return any(
            getattr(enriched, field) is not None for field in ENRICHED_FIELDS
        )

    return _enrich_loop(
        repo, build_enrichers(repo), worth_saving=hubo_datos,
        on_game=on_game, on_progress=on_progress, should_stop=should_stop,
    )


def update_extras(
    repo: LibraryRepository,
    *,
    on_game: Callable[[Game], None] | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> int:
    """
    Vuelve a buscar los datos extra de toda la biblioteca SIN borrar nada.

    Hermana no destructiva de `enrich_all`: mismo recorrido y mismas preguntas
    a HowLongToBeat y a Steam, pero los resultados se escriben ENCIMA de los
    que ya hubiera en vez de partir de una tabla vacía. Devuelve cuántos juegos
    cambiaron de verdad.

    Es la diferencia que importa cuando esto se corta a medias —cerrar la
    ventana, quedarse sin red—: con `enrich_all`, los juegos borrados a los que
    no le dio tiempo a llegar se quedan sin sus datos y no vuelven. Aquí lo
    peor que puede pasar es que la mitad de la biblioteca siga con los datos de
    antes.

    Los enrichers van con `overwrite=True`, y eso es lo que sustituye al
    borrado: sin él no se actualizaría nada, porque los dos se saltan el juego
    que ya tiene valor (y HLTB también el ya buscado sin éxito, `hltb_checked`)
    — vaciar la tabla era justo la forma de esquivar esos atajos. Y como los
    dos devuelven el juego intacto cuando la consulta falla o no encuentra
    nada, un dato bueno nunca se pisa con un None.

    BLOQUEA y tarda: una petición de red por juego.
    """
    from puntueitor.core.enrichers.factory import build_enrichers

    logger.info("actualizando los datos extra de la biblioteca")

    # Aquí los juegos llegan CON sus extras, así que "tiene datos" lo cumple
    # casi cualquiera y no dice nada: lo que se cuenta es que haya cambiado.
    # `Game` es un dataclass y los enrichers usan `replace`, así que comparar
    # vale.
    def cambio(game: Game, enriched: Game) -> bool:
        return enriched != game

    return _enrich_loop(
        repo, build_enrichers(repo, overwrite=True), worth_saving=cambio,
        on_game=on_game, on_progress=on_progress, should_stop=should_stop,
    )


def _enrich_loop(
    repo: LibraryRepository,
    enrichers,
    *,
    worth_saving: Callable[[Game, Game], bool],
    on_game: Callable[[Game], None] | None,
    on_progress: Callable[[int, int, str], None] | None,
    should_stop: Callable[[], bool] | None,
) -> int:
    """
    El recorrido que comparten `enrich_all` y `update_extras`.

    Lo único que las distingue una vez montados los enrichers es qué cuenta
    como resultado que merezca guardarse, y eso entra por `worth_saving`.

    Se guarda juego a juego, no al final: esto dura minutos y cortarlo a la
    mitad no debe tirar lo ya averiguado.
    """
    from puntueitor.core.enrichers.factory import apply_enrichers
    games = list(repo.load())
    total = len(games)
    guardados = 0

    for index, game in enumerate(games, start=1):
        if should_stop is not None and should_stop():
            logger.info(f"enriquecido interrumpido en {index} de {total}")
            break
        if on_progress is not None:
            on_progress(index, total, game.title)

        try:
            enriched = apply_enrichers(game, enrichers)
        except Exception as error:  # noqa: BLE001 - un juego no tumba el lote
            logger.warning(f"no se pudo enriquecer {game.title!r}: {error}")
            continue

        if worth_saving(game, enriched):
            repo.save_game(enriched)
            guardados += 1
            if on_game is not None:
                on_game(enriched)

    logger.info(f"enriquecidos {guardados} de {total} juegos")
    return guardados
