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
    """Resuelve juegos de Amazon (via Heroic) contra IGDB."""

    AMAZON_SOURCE_ID = 20  # amazon_asin

    def __init__(
        self,
        igdb: IGDBService,
        cache_file: str | Path | None = None,
    ):
        self.igdb = igdb
        self.cacher = ResolversCacher(cache_file) if cache_file else None
        self.unknown_cacher = DesconocidosCacher()

    def resolve(self, raw: dict, refresh: bool = False) -> Sequence[Game]:
        """
        raw: dict de Amazon (de Heroic/nile) con 'app_name' y 'title'
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
            if self.cacher and not self.cacher._available:
                logger.warning(f"Amazon: skipping '{title}' — resolver cache unavailable")
                return []

            cleaned_name = title.strip()
            if cleaned_name and len(cleaned_name) >= 2:
                search_name = cleaned_name[:50]
                logger.debug(f"Searching Amazon game by title: {search_name}")
                results = self.igdb.search_by_title(search_name, limit=10, cache_results=True)

                target_ts = self._parse_date(raw)
                best = self._find_best_match_by_date(results, target_ts)

            igdb_ids = [r["id"] for r in results] if results else []

            if not igdb_ids:
                logger.warning(f"Amazon game not found in IGDB: {title} (ID: {amazon_id})")
                self.unknown_cacher.save_unknown("amazon", title, str(amazon_id))

            if self.cacher and igdb_ids:
                self.cacher.set_igdb_ids("amazon", amazon_id, igdb_ids)

        games: list[Game] = []
        for igdb_id in igdb_ids or []:
            raw_game = self.igdb.get_game(igdb_id=igdb_id, refresh=refresh)
            game = IGMapperGame.map_to_game(raw_game)
            game.set_store(Stores.AMAZON, amazon_id)
            games.append(game)

        return games