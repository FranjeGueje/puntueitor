import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ExtrasCacher:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path.home() / ".cache" / "puntueitor" / "puntueitor.db"
        self.db_path = Path(db_path)
        self._available = False
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
            self._available = True
        except Exception as e:
            logger.warning(f"Failed to initialize ExtrasCacher at {self.db_path}: {e}")
            self._available = False

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS extras (
                    id_igdb INTEGER PRIMARY KEY,
                    duration_hours REAL,
                    steam_score REAL,
                    steam_review INTEGER
                )
            """)
            conn.commit()
            try:
                conn.execute("ALTER TABLE extras ADD COLUMN steam_score REAL")
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE extras ADD COLUMN steam_review INTEGER")
                conn.commit()
            except Exception:
                pass

    def get_all_extras(self) -> dict[int, dict]:
        if not self._available:
            return {}
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS extras (id_igdb INTEGER PRIMARY KEY, duration_hours REAL, steam_score REAL, steam_review INTEGER)")
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM extras")
                return {row["id_igdb"]: dict(row) for row in cursor.fetchall()}
        except Exception as e:
            logger.warning(f"Error getting all extras: {e}")
            return {}

    def get_extras(self, igdb_id: int) -> dict:
        if not self._available:
            return {}
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS extras (id_igdb INTEGER PRIMARY KEY, duration_hours REAL, steam_score REAL, steam_review INTEGER)")
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM extras WHERE id_igdb = ?", (igdb_id,))
                row = cursor.fetchone()
                return dict(row) if row else {}
        except Exception as e:
            logger.warning(f"Error getting extras: {e}")
            return {}

    def save_extras(self, igdb_id: int, duration_hours: float | None = None, steam_score: float | None = None, steam_review: int | None = None) -> None:
        if not self._available:
            return

        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS extras (id_igdb INTEGER PRIMARY KEY, duration_hours REAL, steam_score REAL, steam_review INTEGER)")
                conn.execute("""
                    INSERT INTO extras (id_igdb, duration_hours, steam_score, steam_review)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id_igdb) DO UPDATE SET
                        duration_hours=COALESCE(excluded.duration_hours, extras.duration_hours),
                        steam_score=COALESCE(excluded.steam_score, extras.steam_score),
                        steam_review=COALESCE(excluded.steam_review, extras.steam_review)
                """, (igdb_id, duration_hours, steam_score, steam_review))
                conn.commit()
        except Exception as e:
            logger.warning(f"Error saving extras: {e}")

    def clear_all(self) -> None:
        if not self._available:
            return
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute("DELETE FROM extras")
                conn.commit()
        except Exception as e:
            logger.warning(f"Error clearing extras: {e}")
