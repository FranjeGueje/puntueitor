"""
Entradas del carrusel construidas desde tu caché real de IGDB
(`~/.cache/puntueitor/puntueitor.db`), en vez de los datos de ejemplo.

Sigue siendo parte del prototipo visual: lee directamente de la caché local
con `IGDBCacher`/`ResolversCacher`, no pasa por `LibraryService` ni por
`LibraryRepository`. La integración real con la biblioteca llegará en la
siguiente fase.

Eso sí, respeta la misma "Regla de Oro" que `LibraryRepository.load()`
documenta en `arquitectura.md`: la tabla `resolvers` es la única fuente de
verdad de qué está realmente en la biblioteca. La tabla `games` de
`IGDBCacher` es una caché global de *toda* consulta hecha a IGDB — incluye
candidatos de búsqueda descartados al resolver otros juegos (title search
devuelve varios resultados, se cachean todos, se selecciona solo uno). Iterar
`games` directamente (como se hacía antes) colaba esos candidatos huérfanos
en el carrusel: juegos con carátula pero sin ninguna tienda asociada, porque
nunca estuvieron realmente en la biblioteca.
"""
import logging
from pathlib import Path

from puntueitor.core.cachers.igdb_cacher import IGDBCacher
from puntueitor.core.cachers.resolvers_cacher import ResolversCacher
from puntueitor.core.mappers import IGMapperGame
from puntueitor.gui3d.covers import get_cached_cover_path, load_cover_texture
from puntueitor.gui3d.game_case import make_placeholder_texture
from puntueitor.gui3d.store_colors import primary_store_color

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".cache" / "puntueitor" / "puntueitor.db"
DEFAULT_LIMIT = 60
FALLBACK_DESCRIPTION = "Sin descripción disponible."

# La sinopsis de IGDB no tiene límite de longitud (algunas superan los 2000
# caracteres) y la barra inferior sí lo tiene. Los datos de ejemplo ya vienen
# curados y cortos; esto solo recorta el contenido real.
MAX_DESCRIPTION_CHARS = 320


def _truncate(text: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"{cut}..."

def build_real_entries(
    db_path: Path | None = None,
    limit: int = DEFAULT_LIMIT,
) -> tuple[list[dict], list[tuple]] | None:
    """
    Construye entradas del carrusel desde la caché real de IGDB.

    Devuelve `(entries, pending_downloads)`, o None si no hay base de datos o
    no contiene juegos con carátula (para que el llamante recurra a
    `sample_data` sin comprobaciones adicionales).

    - `entries`: listas de dicts listas para `CarouselEntry`. Los juegos sin
      carátula cacheada llevan un color de relleno por tienda.
    - `pending_downloads`: `(key, igdb_id, cover_url)` de los juegos cuya
      carátula real aún no está en disco — el llamante decide cuándo y cómo
      descargarlas (ver `covers.CoverLoader`).
    """
    resolved_db_path = db_path or DEFAULT_DB_PATH
    igdb_cacher = IGDBCacher(resolved_db_path)
    resolvers_cacher = ResolversCacher(resolved_db_path)
    if not igdb_cacher.available or not resolvers_cacher.available:
        logger.info("gui3d: sin caché real de IGDB, usando datos de ejemplo")
        return None

    stores_by_id = resolvers_cacher.get_all_mappings()
    if not stores_by_id:
        logger.info("gui3d: sin juegos en resolvers, usando datos de ejemplo")
        return None

    games_by_id = {g["id"]: g for g in igdb_cacher.get_all_games()}

    # Solo juegos realmente en la biblioteca (con fila en resolvers) y con
    # carátula. Un igdb_id de resolvers sin ficha en games sería un hueco de
    # caché a medio poblar; se ignora en vez de reventar.
    raws = [
        games_by_id[igdb_id]
        for igdb_id in stores_by_id
        if igdb_id in games_by_id and games_by_id[igdb_id].get("cover")
    ]
    if not raws:
        logger.info("gui3d: ningún juego de la biblioteca tiene carátula")
        return None

    # Los juegos con carátula ya descargada van primero, para que el
    # carrusel arranque con la mayor variedad posible de arte real visible.
    raws.sort(key=lambda raw: get_cached_cover_path(raw["id"]) is None)

    entries = []
    pending: list[tuple] = []

    for raw in raws[:limit]:
        game = IGMapperGame.map_to_game(raw)
        # allow_download=False: la descarga de las que faltan se hace en
        # segundo plano vía CoverLoader, no aquí de forma síncrona.
        texture = load_cover_texture(game.igdb_id, game.cover_url, allow_download=False)

        if texture is None:
            stores = set(stores_by_id.get(game.igdb_id, {}))
            texture = make_placeholder_texture(primary_store_color(stores))
            pending.append((game.igdb_id, game.igdb_id, game.cover_url))

        entries.append({
            "key": game.igdb_id,
            "title": game.title,
            "description": _truncate(game.storyline) if game.storyline else FALLBACK_DESCRIPTION,
            "texture": texture,
            "stores": frozenset(stores_by_id.get(game.igdb_id, {})),
        })

    return entries, pending
