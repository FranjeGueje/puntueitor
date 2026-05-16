import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ExtrasCacher:
    def __init__(self, db_path: str | Path):
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
                    duration_hours REAL
                )
            """)
            conn.commit()

    def get_all_extras(self) -> dict[int, dict]:
        if not self._available:
            return {}
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
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
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM extras WHERE id_igdb = ?", (igdb_id,))
                row = cursor.fetchone()
                return dict(row) if row else {}
        except Exception as e:
            logger.warning(f"Error getting extras: {e}")
            return {}

    def save_extras(self, igdb_id: int, duration_hours: float | None) -> None:
        if not self._available:
            return
        if duration_hours is None:
            return
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute("""
                    INSERT INTO extras (id_igdb, duration_hours)
                    VALUES (?, ?)
                    ON CONFLICT(id_igdb) DO UPDATE SET
                        duration_hours=excluded.duration_hours
                """, (igdb_id, duration_hours))
                conn.commit()
        except Exception as e:
            logger.warning(f"Error saving extras: {e}")