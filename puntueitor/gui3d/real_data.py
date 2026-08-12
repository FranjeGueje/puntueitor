"""
Entradas del carrusel construidas desde tu biblioteca real, cacheada en
`~/.cache/puntueitor/`.

Usa `LibraryRepository.load()`, el mismo cargador que la TUI. Antes esto
rehacía a mano la unión de `resolvers` con `games`, lo que servía mientras
al carrusel solo le hacía falta título, descripción y tiendas, pero se
quedaba corto para la ficha: la duración, las puntuaciones de Steam y de
SteamDB no están en la caché de IGDB, viven en la tabla de extras y las
junta el repositorio. Delegar en él evita además repetir aquí la "Regla de
Oro" (`resolvers` es la única fuente de verdad de qué está de verdad en la
biblioteca; la tabla `games` es una caché global de TODA consulta hecha a
IGDB e incluye candidatos de búsqueda descartados, que se colaban en el
carrusel como juegos con carátula pero sin ninguna tienda).

Sigue sin pasar por `LibraryService`: es solo lectura de lo ya cacheado, no
lanza el pipeline ni pide nada a la red.
"""
import logging
from pathlib import Path

from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.gui3d.covers import load_cover_texture
from puntueitor.gui3d.game_case import make_placeholder_texture
from puntueitor.gui3d.store_colors import primary_store_color

logger = logging.getLogger(__name__)


def build_real_entries(
    cache_dir: Path | None = None,
    limit: int | None = None,
) -> tuple[list[dict], list[tuple]] | None:
    """
    Construye entradas del carrusel desde la biblioteca cacheada.

    Sin `limit` entra la biblioteca entera. Antes había un tope de 60 juegos
    puesto mientras esto era un prototipo, que dejaba fuera en silencio el
    95% de una biblioteca de 1273: los cargaba del disco, decía por consola
    que los había cargado, y luego el carrusel solo contenía los 60
    primeros. Medido con la biblioteca real, construir las 1266 cajas cuesta
    1,2 s y unos 270 MB, y navegar sale a 0,5 ms por movimiento, así que el
    tope no hacía falta para nada.

    Devuelve `(entries, pending_downloads)`, o None si no hay biblioteca o
    ninguno de sus juegos tiene carátula (para que el llamante recurra a
    `sample_data` sin comprobaciones adicionales).

    - `entries`: dicts listos para `CarouselEntry`, cada uno con el `Game`
      completo dentro para que la ficha pueda leer sus datos. Los juegos sin
      carátula cacheada llevan un color de relleno por tienda.
    - `pending_downloads`: `(key, igdb_id, cover_url)` de los juegos cuya
      carátula real aún no está en disco. OJO: esto puede ser casi toda la
      biblioteca (con 1273 juegos y 67 carátulas en caché, son 1206), así
      que el llamante NO debe encolarlas todas de golpe — ver
      `app.App._request_nearby_covers`, que solo pide las de alrededor de
      la selección.
    """
    repository = LibraryRepository(cache_dir)
    games = [game for game in repository.load() if game.cover_url]
    if not games:
        logger.info("gui3d: biblioteca vacía o sin carátulas, usando datos de ejemplo")
        return None

    # Orden alfabético. Antes iban primero los que ya tenían la carátula
    # descargada, para que el prototipo arrancara enseñando arte real: eso
    # dejaba la biblioteca en un orden sin sentido para quien la usa
    # (depende de qué JPEG haya en la caché).
    #
    # Este orden ya NO es el que se ve: `app.App` aplica su propia
    # ordenación al arrancar (ver `gui3d/sorting.py`). Se mantiene porque
    # sigue siendo el desempate: `sort` es estable, así que dos juegos con
    # la misma nota o la misma duración salen en orden alfabético en vez de
    # en uno arbitrario.
    games.sort(key=lambda game: game.title_normalized)

    entries = []
    pending: list[tuple] = []

    for game in (games if limit is None else games[:limit]):
        # NINGUNA carátula se carga aquí, ni siquiera las que ya están en
        # disco: todas arrancan con el color de su tienda y el llamante va
        # pidiendo las de alrededor de la selección.
        #
        # Cargar una carátula cuesta 3,4 ms (decodificar el JPEG y subirlo);
        # por 1266 juegos son 4,3 segundos de ventana en negro al arrancar,
        # para acabar enseñando nueve cajas. Las 21 de la primera pantalla
        # cuestan 0,07 s. Esto es lo que hacía que el arranque tardara más
        # cuanto MÁS completa estuviera la caché de carátulas, que es justo
        # al revés de lo que uno espera.
        entries.append({
            "key": game.igdb_id,
            "title": game.title,
            "texture": make_placeholder_texture(primary_store_color(game.stores)),
            "stores": frozenset(game.stores),
            "game": game,
        })
        pending.append((game.igdb_id, game.igdb_id, game.cover_url))

    return entries, pending
