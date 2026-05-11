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


class EpicHeroicResolver(BaseResolver):
    """Resuelve juegos de Epic (via Heroic) contra IGDB."""

    EPIC_SOURCE_ID = 26

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
        raw: dict de Epic (de Heroic/legendary) con 'app_name' y 'title'
        refresh: fuerza refresco de los datos de IGDB para este juego
        """
        epic_id = str(raw.get("app_name", raw.get("id", "")))
        title = raw.get("title", "")

        if not epic_id:
            logger.warning(f"Epic game missing app_name, skipping: {title}")
            return []

        igdb_ids: list[int] | None = None

        if not refresh and self.cacher:
            igdb_ids = self.cacher.get_igdb_ids("epic", epic_id)

        if not igdb_ids:
            results = self.igdb.search_by_external_game(
                source_id=self.EPIC_SOURCE_ID,
                external_uid=epic_id,
                cache_results=True
            )

            if not results:
                cleaned_name = title.strip()
                if cleaned_name and len(cleaned_name) >= 2:
                    search_name = cleaned_name[:50]
                    logger.debug(f"Fallback search for Epic game {epic_id} using title: {search_name}")
                    results = self.igdb.search_by_title(search_name, cache_results=True)
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