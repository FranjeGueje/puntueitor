import logging
from pathlib import Path
from datetime import datetime, timezone
from datetime import datetime, timezone

from puntueitor.core.models import Library, Game, Stores
from puntueitor.core.cachers.igdb_cacher import IGDBCacher
from puntueitor.core.cachers.extras_cacher import ExtrasCacher
from puntueitor.core.cachers.resolvers_cacher import ResolversCacher

logger = logging.getLogger(__name__)


class LibraryRepository:
    """
    Repositorio para gestionar la persistencia de la biblioteca de juegos.
    Cumple la REGLA DE ORO: igdb.sqlite solo contiene datos canónicos.
    La biblioteca se reconstruye uniendo los datos de las tiendas, resolvers y extras.
    """

    def __init__(self, cache_dir: str | Path | None = None):
        if cache_dir is None:
            base_path = Path(__file__).resolve().parents[3]
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
        """Reconstruye la biblioteca desde igdb.sqlite (autoritativo)."""
        all_raw = self.igdb_cacher.get_all_games()
        if not all_raw:
            logger.info("No games in igdb.sqlite, library empty")
            return Library.from_iterable(())

        all_mappings = self.resolvers_cacher.get_all_mappings()
        all_extras = self.extras_cacher.get_all_extras()

        logger.info(f"Loading {len(all_raw)} games from igdb.sqlite")

        games = []
        for raw in all_raw:
            igdb_id = raw["id"]


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

            extras = all_extras.get(igdb_id, {})
            duration_hours = extras.get("duration_hours")

            stores = all_mappings.get(igdb_id, {})

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
        logger.info(f"Built {len(games)} games from cache")
        return Library.from_iterable(games)
