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


class GOGHeroicResolver(BaseResolver):
    """Resuelve juegos de GOG (via Heroic) contra IGDB."""

    GOG_SOURCE_ID = 5

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
        raw: dict de GOG (de Heroic) con 'app_name' y 'title'
        refresh: fuerza refresco de los datos de IGDB para este juego
        """
        gog_id = str(raw.get("app_name", ""))
        title = raw.get("title", "")

        if not gog_id:
            logger.warning(f"GOG game missing ID, skipping: {title}")
            return []

        if self.unknown_cacher.is_unknown("gog", gog_id):
            logger.debug(f"Skipping known unknown GOG game: {title}")
            return []

        igdb_ids: list[int] | None = None

        if not refresh and self.cacher:
            igdb_ids = self.cacher.get_igdb_ids("gog", gog_id)

        if not igdb_ids:
            results = self.igdb.search_by_external_game(
                source_id=self.GOG_SOURCE_ID,
                external_uid=gog_id,
                cache_results=True
            )

            if not results:
                cleaned_name = title.strip()
                if cleaned_name and len(cleaned_name) >= 2:
                    search_name = cleaned_name[:50]
                    logger.debug(f"Fallback search for GOG game {gog_id} using title: {search_name}")
                    results = self.igdb.search_by_title(search_name, cache_results=True)
                else:
                    logger.warning(f"Skipping fallback search for GOG game {gog_id}: invalid title '{title}'")

            igdb_ids = [r["id"] for r in results] if results else []

            if not igdb_ids:
                logger.warning(f"GOG game not found in IGDB: {title} (ID: {gog_id})")
                self.unknown_cacher.save_unknown("gog", title, str(gog_id))

            if self.cacher and igdb_ids:
                self.cacher.set_igdb_ids("gog", gog_id, igdb_ids)

        games: list[Game] = []
        for igdb_id in igdb_ids or []:
            raw_game = self.igdb.get_game(igdb_id=igdb_id, refresh=refresh)
            game = IGMapperGame.map_to_game(raw_game)
            game.set_store(Stores.GOG, gog_id)
            games.append(game)

        return games