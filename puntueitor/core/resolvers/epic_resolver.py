import logging

from puntueitor.core.resolvers.base_resolver import BaseResolver
from puntueitor.core.models import Stores
from puntueitor.core.models.util import similarity

logger = logging.getLogger(__name__)

EPIC_STORE_URL_PREFIX = "https://www.epicgames.com/store/product/"


class EpicHeroicResolver(BaseResolver):
    """Resuelve juegos de Epic (via Heroic) contra IGDB, primero por slug."""

    STORE = Stores.EPIC

    @staticmethod
    def _extract_slug(store_url: str | None) -> str | None:
        if not store_url or not store_url.startswith(EPIC_STORE_URL_PREFIX):
            return None
        return store_url[len(EPIC_STORE_URL_PREFIX):].strip() or None

    @staticmethod
    def _find_best_match(title: str, results: list[dict]) -> dict | None:
        """El candidato con el título más parecido."""
        if not results:
            return None
        if len(results) == 1:
            return results[0]

        normalized = title.lower().strip()
        best = max(
            results,
            key=lambda r: similarity(normalized, (r.get("name") or "").lower()),
        )
        logger.debug(f"Best match for '{title}': '{best.get('name')}'")
        return best

    def _search(self, raw: dict, store_id: str, title: str) -> list[dict] | None:
        slug = self._extract_slug(raw.get("store_url"))
        if slug:
            logger.debug(f"Searching Epic game by slug: {slug}")
            results = self.igdb.search_by_slug(slug, cache_results=True)
            if results:
                return results

        candidates = self._search_by_title(title, store_id)
        if not candidates:
            return candidates

        best = self._find_best_match(title, candidates)
        return [best] if best else []
