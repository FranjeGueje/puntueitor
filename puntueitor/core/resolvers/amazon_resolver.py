import datetime as dt
import logging
from collections.abc import Sequence
from pathlib import Path

from puntueitor.core.resolvers.base_resolver import BaseResolver
from puntueitor.core.igdb import IGDBService
from puntueitor.core.mappers import IGMapperGame
from puntueitor.core.models import Game, Stores

from puntueitor.core.cachers.resolvers_cacher import ResolversCacher
from puntueitor.core.cachers.desconocidos_cacher import DesconocidosCacher

logger = logging.getLogger(__name__)


class AmazonHeroicResolver(BaseResolver):
    """Resuelve juegos de Amazon (via Heroic/nile) contra IGDB.
    Busca por título normalizado y elige el resultado IGDB con la
    fecha de lanzamiento más cercana a extra.releaseDate.
    """

    def __init__(
        self,
        igdb: IGDBService,
        cache_file: str | Path | None = None,
    ):
        self.igdb = igdb
        self.cacher = ResolversCacher(cache_file) if cache_file else None
        self.unknown_cacher = DesconocidosCacher()

    @staticmethod
    def _parse_date(raw: dict) -> int | None:
        """Extrae extra.releaseDate (ISO 8601) y lo convierte a Unix timestamp."""
        extra = raw.get("extra")
        if isinstance(extra, dict):
            date_str = extra.get("releaseDate")
            if date_str:
                try:
                    d = dt.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    return int(d.timestamp())
                except (ValueError, TypeError):
                    pass
        return None

    @staticmethod
    def _find_best_match_by_date(
        results: list[dict], target_ts: int | None
    ) -> dict | None:
        """De una lista de resultados IGDB, elige el que tenga
        first_release_date más cercano a target_ts."""
        if not results:
            return None
        if len(results) == 1:
            return results[0]
        if target_ts is None:
            return results[0]

        best = None
        best_diff = float("inf")
        for r in results:
            ts = r.get("first_release_date")
            if ts is None:
                continue
            diff = abs(int(ts) - target_ts)
            if diff < best_diff:
                best_diff = diff
                best = r

        return best or results[0]

    def resolve(self, raw: dict, refresh: bool = False) -> Sequence[Game]:
        """
        raw: dict de Amazon (de Heroic/nile) con 'app_name', 'title' y 'extra'
        refresh: fuerza refresco de los datos de IGDB para este juego
        """
        amazon_id = str(raw.get("app_name", raw.get("id", "")))
        title = raw.get("title", "")

        if not amazon_id:
            logger.warning(f"Amazon game missing ID, skipping: {title}")
            return []

        if self.unknown_cacher.is_unknown("amazon", amazon_id):
            logger.debug(f"Skipping known unknown Amazon game: {title}")
            return []

        igdb_ids: list[int] | None = None

        if not refresh and self.cacher:
            igdb_ids = self.cacher.get_igdb_ids("amazon", amazon_id)

        if not igdb_ids:
            cleaned_name = title.strip()
            if cleaned_name and len(cleaned_name) >= 2:
                search_name = cleaned_name[:50]
                logger.debug(f"Searching Amazon game by title: {search_name}")
                results = self.igdb.search_by_title(search_name, limit=10, cache_results=True)

                target_ts = self._parse_date(raw)
                best = self._find_best_match_by_date(results, target_ts)

                igdb_ids = [best["id"]] if best else []

                if not igdb_ids:
                    logger.warning(f"Amazon game not found in IGDB: {title} (ID: {amazon_id})")
                    self.unknown_cacher.save_unknown("amazon", title, str(amazon_id))

                if self.cacher and igdb_ids:
                    self.cacher.set_igdb_ids("amazon", amazon_id, igdb_ids)
            else:
                logger.warning(f"Skipping Amazon game {amazon_id}: invalid title '{title}'")
                return []

        games: list[Game] = []
        for igdb_id in igdb_ids or []:
            raw_game = self.igdb.get_game(igdb_id=igdb_id, refresh=refresh)
            game = IGMapperGame.map_to_game(raw_game)
            game.set_store(Stores.AMAZON, amazon_id)
            games.append(game)

        return games