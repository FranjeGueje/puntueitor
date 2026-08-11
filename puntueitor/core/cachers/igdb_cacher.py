import json
import logging

from puntueitor.core.cachers.base_cacher import BaseCacher

logger = logging.getLogger(__name__)

STEAM_EXTERNAL_SOURCE_ID = 1

_UPSERT_GAME = """
    INSERT INTO games (
        id, aggregated_rating, cover, first_release_date,
        genres, name, rating, storyline, total_rating, steam_id
    ) VALUES (
        :id, :aggregated_rating, :cover, :first_release_date,
        :genres, :name, :rating, :storyline, :total_rating, :steam_id
    )
    ON CONFLICT(id) DO UPDATE SET
        aggregated_rating=excluded.aggregated_rating,
        cover=excluded.cover,
        first_release_date=excluded.first_release_date,
        genres=excluded.genres,
        name=excluded.name,
        rating=excluded.rating,
        storyline=excluded.storyline,
        total_rating=excluded.total_rating,
        steam_id=excluded.steam_id
"""


class IGDBCacher(BaseCacher):
    """Caché de las fichas canónicas devueltas por IGDB."""

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY,
            aggregated_rating REAL,
            cover JSON,
            first_release_date INTEGER,
            genres JSON,
            name TEXT,
            rating REAL,
            storyline TEXT,
            total_rating REAL,
            steam_id INTEGER DEFAULT 0
        );
    """

    MIGRATIONS = (
        "ALTER TABLE games ADD COLUMN steam_id INTEGER DEFAULT 0",
    )

    @staticmethod
    def _decode(row) -> dict:
        game = dict(row)
        for field in ("cover", "genres"):
            if game.get(field):
                try:
                    game[field] = json.loads(game[field])
                except (json.JSONDecodeError, TypeError):
                    game[field] = None
        return game

    @staticmethod
    def _extract_steam_id(game_dict: dict) -> int:
        for external in game_dict.get("external_games") or ():
            if not isinstance(external, dict):
                continue
            if external.get("external_game_source") != STEAM_EXTERNAL_SOURCE_ID:
                continue
            try:
                return int(external["uid"])
            except (KeyError, ValueError, TypeError):
                return 0
        return 0

    def get_game(self, igdb_id: int) -> dict | None:
        rows = self._query("SELECT * FROM games WHERE id = ?", (igdb_id,))
        return self._decode(rows[0]) if rows else None

    def get_all_games(self) -> list[dict]:
        return [self._decode(row) for row in self._query("SELECT * FROM games")]

    def save_game(self, game_dict: dict) -> None:
        cover = game_dict.get("cover")
        genres = game_dict.get("genres")
        self._write(_UPSERT_GAME, {
            "id": game_dict.get("id"),
            "aggregated_rating": game_dict.get("aggregated_rating"),
            "cover": json.dumps(cover) if cover else None,
            "first_release_date": game_dict.get("first_release_date"),
            "genres": json.dumps(genres) if genres else None,
            "name": game_dict.get("name"),
            "rating": game_dict.get("rating"),
            "storyline": game_dict.get("storyline"),
            "total_rating": game_dict.get("total_rating"),
            "steam_id": self._extract_steam_id(game_dict),
        })

    def get_all_genres(self) -> list[str]:
        genres: set[str] = set()
        for row in self._query("SELECT genres FROM games WHERE genres IS NOT NULL"):
            if not row[0]:
                continue
            try:
                parsed = json.loads(row[0])
            except json.JSONDecodeError:
                continue
            for entry in parsed or ():
                if isinstance(entry, dict) and "name" in entry:
                    genres.add(entry["name"])
                elif isinstance(entry, str):
                    genres.add(entry)
        return sorted(genres)
