import sqlite3
import json
import time
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class IGDBCacher:
    DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60

    def __init__(self, db_path: str | Path, ttl_seconds: int | None = None):
        self.db_path = Path(db_path)
        self.ttl_seconds = ttl_seconds or self.DEFAULT_TTL_SECONDS
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
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
                    _schema_version INTEGER,
                    cached_at INTEGER
                )
            """)
            conn.commit()

    def _is_cache_valid(self, cached_at: int | None) -> bool:
        if cached_at is None:
            return True  # Cache sin timestamp = válida (legacy compatibility)
        return (time.time() - cached_at) < self.ttl_seconds

    def get_game(self, igdb_id: int) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM games WHERE id = ?", (igdb_id,))
            row = cursor.fetchone()
            if row:
                res = dict(row)
                cached_at = res.get("cached_at")

                if not self._is_cache_valid(cached_at):
                    logger.debug(f"Cache expired for game {igdb_id}")
                    return None

                if res.get("cover"):
                    res["cover"] = json.loads(res["cover"])
                if res.get("genres"):
                    res["genres"] = json.loads(res["genres"])
                return res
            return None

    def save_game(self, game_dict: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
            data = {
                "id": game_dict.get("id"),
                "aggregated_rating": game_dict.get("aggregated_rating"),
                "cover": json.dumps(game_dict.get("cover")) if game_dict.get("cover") else None,
                "first_release_date": game_dict.get("first_release_date"),
                "genres": json.dumps(game_dict.get("genres")) if game_dict.get("genres") else None,
                "name": game_dict.get("name"),
                "rating": game_dict.get("rating"),
                "storyline": game_dict.get("storyline"),
                "total_rating": game_dict.get("total_rating"),
                "_schema_version": game_dict.get("_schema_version"),
                "cached_at": int(time.time())
            }

            conn.execute("""
                INSERT INTO games (
                    id, aggregated_rating, cover, first_release_date,
                    genres, name, rating, storyline, total_rating, _schema_version, cached_at
                ) VALUES (
                    :id, :aggregated_rating, :cover, :first_release_date,
                    :genres, :name, :rating, :storyline, :total_rating, :_schema_version, :cached_at
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
                    _schema_version=excluded._schema_version,
                    cached_at=excluded.cached_at
            """, data)
            conn.commit()

    def get_all_cached_ids(self) -> list[int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id FROM games")
            return [row[0] for row in cursor.fetchall()]

    def get_all_genres(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT genres FROM games WHERE genres IS NOT NULL")
            all_genres: set[str] = set()
            for row in cursor.fetchall():
                if row[0]:
                    try:
                        genres_list = json.loads(row[0])
                        if genres_list:
                            for g in genres_list:
                                if isinstance(g, dict) and "name" in g:
                                    all_genres.add(g["name"])
                                elif isinstance(g, str):
                                    all_genres.add(g)
                    except json.JSONDecodeError:
                        continue
            return sorted(all_genres)
