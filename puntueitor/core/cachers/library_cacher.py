import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LibraryCacher:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path.home() / ".config" / "puntueitor" / "library.sqlite"
        self.db_path = Path(db_path)
        self._available = False
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
            self._available = True
        except Exception as e:
            logger.warning(f"Failed to initialize LibraryCacher at {self.db_path}: {e}")
            self._available = False

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_games (
                    igdb_id INTEGER PRIMARY KEY,
                    finished INTEGER NOT NULL DEFAULT 0,
                    hidden INTEGER NOT NULL DEFAULT 0,
                    backlog INTEGER NOT NULL DEFAULT 0,
                    favorite INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.commit()

    def _ensure_table(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_games (
                igdb_id INTEGER PRIMARY KEY,
                finished INTEGER NOT NULL DEFAULT 0,
                hidden INTEGER NOT NULL DEFAULT 0,
                backlog INTEGER NOT NULL DEFAULT 0,
                favorite INTEGER NOT NULL DEFAULT 0
            )
        """)

    def get_status(self, igdb_id: int) -> dict:
        if not self._available:
            return {}
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                self._ensure_table(conn)
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM user_games WHERE igdb_id = ?", (igdb_id,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "finished": bool(row["finished"]),
                        "hidden": bool(row["hidden"]),
                        "backlog": bool(row["backlog"]),
                        "favorite": bool(row["favorite"]),
                    }
                return {}
        except Exception as e:
            logger.warning(f"Error getting status for {igdb_id}: {e}")
            return {}

    def set_status(self, igdb_id: int, finished: bool = False, hidden: bool = False,
                   backlog: bool = False, favorite: bool = False) -> None:
        if not self._available:
            return
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                self._ensure_table(conn)
                conn.execute("""
                    INSERT INTO user_games (igdb_id, finished, hidden, backlog, favorite)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(igdb_id) DO UPDATE SET
                        finished = excluded.finished,
                        hidden = excluded.hidden,
                        backlog = excluded.backlog,
                        favorite = excluded.favorite
                """, (igdb_id, int(finished), int(hidden), int(backlog), int(favorite)))
                conn.commit()
        except Exception as e:
            logger.warning(f"Error setting status for {igdb_id}: {e}")

    def get_all_statuses(self) -> dict[int, dict]:
        if not self._available:
            return {}
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                self._ensure_table(conn)
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM user_games")
                result = {}
                for row in cursor.fetchall():
                    result[row["igdb_id"]] = {
                        "finished": bool(row["finished"]),
                        "hidden": bool(row["hidden"]),
                        "backlog": bool(row["backlog"]),
                        "favorite": bool(row["favorite"]),
                    }
                return result
        except Exception as e:
            logger.warning(f"Error getting all statuses: {e}")
            return {}
