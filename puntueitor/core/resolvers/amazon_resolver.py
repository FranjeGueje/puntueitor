import datetime as dt
import logging

from puntueitor.core.resolvers.base_resolver import BaseResolver
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)


class AmazonHeroicResolver(BaseResolver):
    """
    Resuelve juegos de Amazon (via Heroic/nile) contra IGDB.

    Amazon no expone un id que IGDB conozca, así que busca por título y
    desempata con la fecha de lanzamiento más cercana a extra.releaseDate.
    """

    STORE = Stores.AMAZON

    @staticmethod
    def _parse_date(raw: dict) -> int | None:
        """Extrae extra.releaseDate (ISO 8601) como timestamp Unix."""
        extra = raw.get("extra")
        if not isinstance(extra, dict):
            return None

        date_str = extra.get("releaseDate")
        if not date_str:
            return None

        try:
            parsed = dt.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return int(parsed.timestamp())
        except (ValueError, TypeError, AttributeError):
            return None

    @staticmethod
    def _find_best_match_by_date(
        results: list[dict], target_ts: int | None
    ) -> dict | None:
        """El candidato con first_release_date más cercano a target_ts."""
        if not results:
            return None
        if len(results) == 1 or target_ts is None:
            return results[0]

        dated = [r for r in results if r.get("first_release_date") is not None]
        if not dated:
            return results[0]

        return min(dated, key=lambda r: abs(int(r["first_release_date"]) - target_ts))

    def _search(self, raw: dict, store_id: str, title: str) -> list[dict] | None:
        candidates = self._search_by_title(title, store_id, limit=10)
        if not candidates:
            return candidates

        best = self._find_best_match_by_date(candidates, self._parse_date(raw))
        return [best] if best else []
