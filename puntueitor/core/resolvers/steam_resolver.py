import logging

from puntueitor.core.resolvers.base_resolver import BaseResolver
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)


class SteamIGDBResolver(BaseResolver):
    """Resuelve juegos de Steam contra IGDB por su appid."""

    STORE = Stores.STEAM
    STEAM_SOURCE_ID = 1

    def _extract_id(self, raw: dict) -> str:
        return str(raw.get("appid") or "")

    def _search(self, raw: dict, store_id: str, title: str) -> list[dict] | None:
        results = self.igdb.search_by_external_game(
            source_id=self.STEAM_SOURCE_ID,
            external_uid=store_id,
            cache_results=True,
        )
        if results:
            return results

        return self._search_by_title(title, store_id)
