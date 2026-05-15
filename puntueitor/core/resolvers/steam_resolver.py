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

class SteamIGDBResolver(BaseResolver):
    """Resuelve juegos de Steam contra IGDB y devuelve Games"""
    
    STEAM_SOURCE_ID = 1
    
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
        raw: dict de Steam con 'appid' y 'name'
        refresh: fuerza refresco de los datos de IGDB para este juego
        """
        appid = str(raw["appid"])
        name = raw.get("name", "")

        # Si el juego está en la lista de desconocidos, no buscar en IGDB
        if self.unknown_cacher.is_unknown("steam", appid):
            logger.debug(f"Skipping known unknown Steam game: {name}")
            return []

        igdb_ids: list[int] | None = None

        # Intentar usar caché si no estamos forzando recarga
        if not refresh and self.cacher:
            igdb_ids = self.cacher.get_igdb_ids("steam", appid)
        
        # Si no hay resolución, buscar en IGDB por external_game
        if not igdb_ids:
            results = self.igdb.search_by_external_game(
                source_id=self.STEAM_SOURCE_ID,
                external_uid=appid,
                cache_results=True
            )

            if not results:
                cleaned_name = name.strip()
                if cleaned_name and len(cleaned_name) >= 2:
                    search_name = cleaned_name[:50]
                    logger.debug(f"Fallback search for Steam app {appid} using title: {search_name}")
                    results = self.igdb.search_by_title(search_name, cache_results=True)
                else:
                    logger.warning(f"Skipping fallback search for app {appid}: invalid name '{name}'")
            
            igdb_ids = [r["id"] for r in results]

            if not igdb_ids:
                logger.warning(f"Steam game not found in IGDB: {name} (ID: {appid})")
                self.unknown_cacher.save_unknown("steam", name, str(appid))

            # Guardar correlación
            if self.cacher and igdb_ids:
                self.cacher.set_igdb_ids("steam", appid, igdb_ids)

        # Construir objetos Game usando caché IGDB
        games: list[Game] = []
        for igdb_id in igdb_ids or []:
            raw_game = self.igdb.get_game(igdb_id=igdb_id, refresh=refresh)
            game = IGMapperGame.map_to_game(raw_game)
            game.set_store(Stores.STEAM, appid)
            games.append(game)

        return games
    