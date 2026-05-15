import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from puntueitor.core.models import Library, Game, Stores
from puntueitor.core.cachers.igdb_cacher import IGDBCacher
from puntueitor.core.cachers.extras_cacher import ExtrasCacher
from puntueitor.core.cachers.resolvers_cacher import ResolversCacher
from puntueitor.core.cachers.steam_user_cacher import SteamUserCacher
from puntueitor.core.heroics.loader import HeroicsLoader

logger = logging.getLogger(__name__)


class LibraryRepository:
    """
    Repositorio para gestionar la persistencia de la biblioteca de juegos.
    Cumple la REGLA DE ORO: igdb.sqlite solo contiene datos canónicos.
    La biblioteca se reconstruye uniendo los datos de las tiendas, resolvers y extras.
    """

    def __init__(self, cache_dir: str | Path | None = None):
        if cache_dir is None:
            base_path = Path(__file__).parent.parent.parent
            cache_dir = base_path / "cache"
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.igdb_cacher = IGDBCacher(self.cache_dir / "igdb.sqlite")
        self.extras_cacher = ExtrasCacher(self.cache_dir / "extras.sqlite")
        self.resolvers_cacher = ResolversCacher(self.cache_dir / "resolvers.sqlite")
        self.library_cacher = LibraryCacher()
        self.unknown_cacher = DesconocidosCacher()

    def save(self, library: Library, path: str | Path | None = None) -> None:
        """
        Guarda los campos no canónicos (extras) en extras.sqlite.
        Los datos canónicos ya se guardan en igdb.sqlite durante el pipeline.
        Las relaciones se guardan en resolvers.sqlite durante el pipeline.
        """
        for game in library:
            self.save_game(game)

    def save_game(self, game: Game) -> None:
        """Persiste los extras de un solo juego."""
        if game.duration_hours is not None:
            self.extras_cacher.save_extras(game.igdb_id, game.duration_hours)

    def load(self, path: str | Path | None = None) -> Library:
        """
        Reconstruye la biblioteca realizando un join entre las bases de datos.
        Carga juegos de Steam y de Heroic (GOG, Epic, Amazon).
        """
        config = ConfigManager().get
        steam_id = config.steam_user_id

        # Si no hay Steam ID ni Heroic activo, retornar vacío
        if not steam_id and not config.heroic_is_active:
            logger.info("No Steam ID nor Heroic active, returning empty library")
            return Library.from_iterable(())

        # Obtener TODOS los mappings de resolvers.sqlite (1 solo query)
        all_mappings = self.resolvers_cacher.get_all_mappings()
        logger.info(f"Total mappings in resolvers.sqlite: {len(all_mappings)}")
        for store_name, store_ids in all_mappings.items():
            logger.info(f"  - {store_name}: {len(store_ids)} IGDB IDs")

        # 1. Obtener apps de Steam si está activo
        steam_apps = []
        if steam_id and config.steam_is_active:
            steam_cacher = SteamUserCacher(steam_id)
            steam_apps = steam_cacher.get_all_games()
            logger.info(f"Steam apps loaded: {len(steam_apps)}")

        # 2. Obtener juegos de Heroic si está activo
        heroic_games = []
        if config.heroic_is_active:
            heroic_loader = HeroicsLoader()
            heroic_path = heroic_loader.find_heroic_path(config.heroic_path or None)
            if heroic_path:
                heroic_games = heroic_loader.get_all_heroic_games(heroic_path)
                logger.info(f"Heroic games loaded: {sum(len(g) for g in heroic_games.values())}")
                for store, games in heroic_games.items():
                    logger.info(f"  - {store}: {len(games)} games")
            else:
                logger.warning("Heroic path not found, skipping Heroic games")

        # 3. Construir reverse index para búsquedas rápidas: {(store, store_id): [igdb_id]}
        store_to_igdb: dict[tuple[str, str], list[int]] = {}
        for ig_id, stores in all_mappings.items():
            for store, store_id in stores.items():
                key = (store.value, store_id)
                if key not in store_to_igdb:
                    store_to_igdb[key] = []
                store_to_igdb[key].append(ig_id)

        # 4. Construir mapping igdb_id -> stores
        igdb_to_stores: dict[int, dict[Stores, str]] = {}

        steam_matched = 0
        steam_not_found = 0

        # Procesar Steam apps usando el índice
        for app in steam_apps:
            appid = str(app["appid"])
            key = ("steam", appid)
            if key in store_to_igdb:
                steam_matched += 1
                for ig_id in store_to_igdb[key]:
                    if ig_id not in igdb_to_stores:
                        igdb_to_stores[ig_id] = {}
                    igdb_to_stores[ig_id][Stores.STEAM] = appid
            else:
                steam_not_found += 1

        logger.info(f"Steam matching: {steam_matched} matched, {steam_not_found} not found in cache")

        # Procesar juegos de Heroic usando el índice
        heroics_matched = 0
        heroics_not_found = 0

        for store_name, games in heroic_games.items():
            store_key = store_name.lower()
            store_enum = Stores(store_key)
            for game_data in games:
                store_id = game_data.get("app_name") or game_data.get("id", "")
                if not store_id:
                    continue

                key = (store_key, str(store_id))
                if key in store_to_igdb:
                    heroics_matched += 1
                    for ig_id in store_to_igdb[key]:
                        if ig_id not in igdb_to_stores:
                            igdb_to_stores[ig_id] = {}
                        igdb_to_stores[ig_id][store_enum] = str(store_id)
                else:
                    heroics_not_found += 1

        logger.info(f"Heroic matching: {heroics_matched} matched, {heroics_not_found} not found in cache")

        # Si no hay juegos mapeados, retornar vacío
        if not igdb_to_stores:
            logger.info("No games found in library")
            return Library.from_iterable(())

        # 4. Cargar detalles canónicos de igdb.sqlite y extras de extras.sqlite
        games = []
        for igdb_id, stores in all_mappings.items():
            raw = all_games.get(igdb_id)
            if not raw:
                logger.warning(f"Game {igdb_id} in resolvers but not in igdb cache, skipping")
                continue


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

            user_flags = all_user_flags.get(igdb_id, {})

            game = Game(
                igdb_id=igdb_id,
                title=raw["name"],
                genres=tuple(genres),
                storyline=raw.get("storyline"),
                critic_score=raw.get("aggregated_rating"),
                user_score=raw.get("rating"),
                release_date=release_date,
                cover_url=cover_url,
                duration_hours=duration_hours,
                stores=stores,
                finished=user_flags.get("finished", False),
                hidden=user_flags.get("hidden", False),
                backlog=user_flags.get("backlog", False),
                favorite=user_flags.get("favorite", False),
            )
            games.append(game)

        logger.info(f"Built {len(games)} games from cache")
        return Library.from_iterable(games)
