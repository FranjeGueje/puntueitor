import logging
import sqlite3
import json
from pathlib import Path
from datetime import date, datetime, timezone

from puntueitor.core.models import Library, Game, Stores
from puntueitor.core.config import ConfigManager
from puntueitor.core.cachers.igdb_cacher import IGDBCacher
from puntueitor.core.cachers.extras_cacher import ExtrasCacher
from puntueitor.core.cachers.resolvers_cacher import ResolversCacher
from puntueitor.core.cachers.steam_user_cacher import SteamUserCacher

logger = logging.getLogger(__name__)


class LibraryRepository:
    """
    Repositorio para gestionar la persistencia de la biblioteca de juegos.
    Cumple la REGLA DE ORO: igdb.sqlite solo contiene datos canónicos.
    La biblioteca se reconstruye uniendo los datos de las tiendas, resolvers y extras.
    """

    def __init__(self, cache_dir: str | Path = "cache"):
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.igdb_cacher = IGDBCacher(self.cache_dir / "igdb.sqlite")
        self.extras_cacher = ExtrasCacher(self.cache_dir / "extras.sqlite")
        self.resolvers_cacher = ResolversCacher(self.cache_dir / "resolvers.sqlite")

    def save(self, library: Library, path: str | Path | None = None) -> None:
        """
        Guarda los campos no canónicos (extras) en extras.sqlite.
        Los datos canónicos ya se guardan en igdb.sqlite durante el pipeline.
        Las relaciones se guardan en resolvers.sqlite durante el pipeline.
        """
        for game in library:
            if game.duration_hours is not None:
                self.extras_cacher.save_extras(game.igdb_id, game.duration_hours)

    def load(self, path: str | Path | None = None) -> Library:
        """
        Reconstruye la biblioteca realizando un join entre las bases de datos.
        """
        config = ConfigManager().get
        steam_id = config.steam_user_id
        if not steam_id:
            return Library.from_iterable(())

        # 1. Obtener apps del usuario desde su DB de Steam (ubicada en ~/.cache/puntueitor)
        steam_cacher = SteamUserCacher(steam_id)
        steam_apps = steam_cacher.get_all_games()
        if not steam_apps:
            return Library.from_iterable(())

        # 2. Mapear AppIDs a IGDB IDs usando resolvers.sqlite
        # Recogemos también la relación inversa para reconstruir el objeto Game
        igdb_to_stores = {} # {igdb_id: {Stores.STEAM: appid}}
        
        for app in steam_apps:
            appid = str(app["appid"])
            ig_ids = self.resolvers_cacher.get_igdb_ids("steam", appid)
            if ig_ids:
                for ig_id in ig_ids:
                    if ig_id not in igdb_to_stores:
                        igdb_to_stores[ig_id] = {}
                    igdb_to_stores[ig_id][Stores.STEAM] = appid

        # 3. Cargar detalles canónicos de igdb.sqlite y extras de extras.sqlite
        games = []
        for igdb_id, stores in igdb_to_stores.items():
            raw = self.igdb_cacher.get_game(igdb_id)
            if not raw:
                logger.warning(f"IGDB data not found for resolved game {igdb_id}, skipping")
                continue
            
            # Mapeo respetando nombres de IGDB en la BBDD
            # BBDD: id, name, aggregated_rating, rating, storyline, first_release_date, cover, genres
            
            release_date = None
            ts = raw.get("first_release_date")
            if ts:
                try:
                    release_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
                except (ValueError, OSError, OverflowError):
                    pass

            cover_url = None
            cover_json = raw.get("cover")
            if cover_json and isinstance(cover_json, dict) and "url" in cover_json:
                cover_t = cover_json["url"]
                cover_url = "https:" + cover_t.replace("t_thumb", "t_cover_big")

            genres = []
            genres_json = raw.get("genres")
            if genres_json and isinstance(genres_json, list):
                for g in genres_json:
                    if isinstance(g, dict) and "name" in g:
                        genres.append(g["name"])
            
            extras = self.extras_cacher.get_extras(igdb_id)
            duration_hours = extras.get("duration_hours")

            game = Game(
                igdb_id=raw["id"],
                title=raw["name"],
                genres=tuple(genres),
                storyline=raw.get("storyline"),
                critic_score=raw.get("aggregated_rating"),
                user_score=raw.get("rating"),
                release_date=release_date,
                cover_url=cover_url,
                duration_hours=duration_hours,
                stores=stores
            )
            games.append(game)

        return Library.from_iterable(games)
