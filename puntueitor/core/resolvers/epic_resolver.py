import logging
from collections.abc import Sequence
from pathlib import Path

from puntueitor.core.resolvers.base_resolver import BaseResolver
from puntueitor.core.igdb import IGDBService
from puntueitor.core.mappers import IGMapperGame
from puntueitor.core.models import Game, Stores
from puntueitor.core.models.util import similarity

from puntueitor.core.cachers.resolvers_cacher import ResolversCacher
from puntueitor.core.cachers.desconocidos_cacher import DesconocidosCacher

logger = logging.getLogger(__name__)

EPIC_STORE_URL_PREFIX = "https://www.epicgames.com/store/product/"


class EpicHeroicResolver(BaseResolver):
    """Resuelve juegos de Epic (via Heroic) contra IGDB."""

    def __init__(
        self,
        igdb: IGDBService,
        cache_file: str | Path | None = None,
    ):
        self.igdb = igdb
        self.cacher = ResolversCacher(cache_file) if cache_file else None
        self.unknown_cacher = DesconocidosCacher()

    def _extract_slug(self, store_url: str | None) -> str | None:
        """Extrae el slug de la URL de Epic."""
        if not store_url:
            return None
        if store_url.startswith(EPIC_STORE_URL_PREFIX):
            return store_url[len(EPIC_STORE_URL_PREFIX):].strip()
        return None

    def _find_best_match(self, title: str, results: list[dict]) -> dict | None:
        """Encuentra el mejor match usando similarity."""
        if not results:
            return None
        if len(results) == 1:
            return results[0]

        normalized_title = title.lower().strip()
        best_match = None
        best_score = 0.0

        for r in results:
            igdb_title = r.get("name", "")
            score = similarity(normalized_title, igdb_title.lower())
            if best_match is None or score > best_score:
                best_score = score
                best_match = r

        if best_match is not None:
            logger.debug(f"Best match for '{title}': '{best_match.get('name')}' (score: {best_score:.2f})")
        return best_match

    def resolve(self, raw: dict, refresh: bool = False) -> Sequence[Game]:
        """
        raw: dict de Epic (de Heroic/legendary) con 'app_name', 'title', 'store_url'
        refresh: fuerza refresco de los datos de IGDB para este juego
        """
        epic_id = str(raw.get("app_name", raw.get("id", "")))
        title = raw.get("title", "")
        store_url = raw.get("store_url", "")

        if not epic_id:
            logger.warning(f"Epic game missing app_name, skipping: {title}")
            return []

        if self.unknown_cacher.is_unknown("epic", epic_id):
            logger.debug(f"Skipping known unknown Epic game: {title}")
            return []

        igdb_ids: list[int] | None = None

        if not refresh and self.cacher:
            igdb_ids = self.cacher.get_igdb_ids("epic", epic_id)

        if not igdb_ids:
            if self.cacher and not self.cacher._available:
                logger.warning(f"Epic: skipping '{title}' — resolver cache unavailable")
                return []

            results = []

            slug = self._extract_slug(store_url)
            if slug:
                logger.debug(f"Searching Epic game by slug: {slug}")
                results = self.igdb.search_by_slug(slug, cache_results=True)

            if not results:
                cleaned_name = title.strip()
                if cleaned_name and len(cleaned_name) >= 2:
                    search_name = cleaned_name[:50]
                    logger.debug(f"Fallback search for Epic game {epic_id} using title: {search_name}")
                    title_results = self.igdb.search_by_title(search_name, cache_results=True)
                    best_match = self._find_best_match(title, title_results)
                    if best_match:
                        results = [best_match]
                else:
                    logger.warning(f"Skipping fallback search for Epic game {epic_id}: invalid title '{title}'")

            igdb_ids = [r["id"] for r in results] if results else []

            if not igdb_ids:
                logger.warning(f"Epic game not found in IGDB: {title} (ID: {epic_id})")
                self.unknown_cacher.save_unknown("epic", title, str(epic_id))

            if self.cacher and igdb_ids:
                self.cacher.set_igdb_ids("epic", epic_id, igdb_ids)

        games: list[Game] = []
        for igdb_id in igdb_ids or []:
            raw_game = self.igdb.get_game(igdb_id=igdb_id, refresh=refresh)
            game = IGMapperGame.map_to_game(raw_game)
            game.set_store(Stores.EPIC, epic_id)
            games.append(game)

        return games