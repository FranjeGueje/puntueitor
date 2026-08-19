import logging

from puntueitor.core.resolvers.base_resolver import BaseResolver
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)


class GOGResolver(BaseResolver):
    """Resuelve juegos de GOG contra IGDB por su id de producto."""

    STORE = Stores.GOG
    GOG_SOURCE_ID = 5

    def _extract_id(self, raw: dict) -> str:
        return str(raw.get("app_name") or "")

    def _search(self, raw: dict, store_id: str, title: str) -> list[dict] | None:
        results = self.igdb.search_by_external_game(
            source_id=self.GOG_SOURCE_ID,
            external_uid=store_id,
            cache_results=True,
        )
        if results:
            return results

        return self._search_by_title(title, store_id)
