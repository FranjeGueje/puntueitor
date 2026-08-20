import logging

from puntueitor.core.resolvers.base_resolver import BaseResolver
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)


class ItchioResolver(BaseResolver):
    """
    Resuelve juegos de itch.io contra IGDB por su id de producto.

    IGDB SÍ indexa itch.io como fuente externa (`external_game_sources.id ==
    30`, nombre "Itchio"; comprobado contra la API real, no por documentación
    de terceros). Su `uid` es el mismo `game.id` numérico que devuelve
    `owned-keys` — no hace falta ningún mapeo.
    """

    STORE = Stores.ITCHIO
    ITCHIO_SOURCE_ID = 30

    def _extract_id(self, raw: dict) -> str:
        return str(raw.get("app_name") or "")

    def _search(self, raw: dict, store_id: str, title: str) -> list[dict] | None:
        results = self.igdb.search_by_external_game(
            source_id=self.ITCHIO_SOURCE_ID,
            external_uid=store_id,
            cache_results=True,
        )
        if results:
            return results

        return self._search_by_title(title, store_id)
