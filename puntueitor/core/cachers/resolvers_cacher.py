import sqlite3
import logging
from pathlib import Path
from typing import Sequence

from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)


class ResolversCacher:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._available = False
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
            self._available = True
        except Exception as e:
            logger.warning(f"Failed to initialize ResolversCacher at {self.db_path}: {e}")
            self._available = False

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resolvers (
                    store TEXT,
                    id_store TEXT,
                    id_igdb INTEGER,
                    PRIMARY KEY (store, id_store, id_igdb)
                )
            """)
            conn.commit()

    def get_igdb_ids(self, store: str, id_store: str) -> list[int] | None:
        if not self._available:
            return None
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cursor = conn.execute(
                    "SELECT id_igdb FROM resolvers WHERE store = ? AND id_store = ?",
                    (store, str(id_store))
                )
                rows = cursor.fetchall()
                if rows:
                    return [row[0] for row in rows]
                return None
        except Exception as e:
            logger.warning(f"Error getting igdb ids: {e}")
            self._available = False
            return None

    def set_igdb_ids(self, store: str, id_store: str, igdb_ids: Sequence[int]) -> None:
        if not self._available:
            return
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute(
                    "DELETE FROM resolvers WHERE store = ? AND id_store = ?",
                    (store, str(id_store))
                )
                conn.executemany(
                    "INSERT INTO resolvers (store, id_store, id_igdb) VALUES (?, ?, ?)",
                    [(store, str(id_store), igdb_id) for igdb_id in igdb_ids]
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Error setting igdb ids: {e}")

    def get_all_mappings(self) -> dict[int, dict[Stores, str]]:
        """Returns: {igdb_id: {Stores: store_id, ...}}"""
        if not self._available:
            return {}
        result: dict[int, dict[Stores, str]] = {}
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cursor = conn.execute("SELECT store, id_store, id_igdb FROM resolvers")
                for store_str, id_store, igdb_id in cursor.fetchall():
                    try:
                        store = Stores(store_str)
                    except ValueError:
                        continue
                    if igdb_id not in result:
                        result[igdb_id] = {}
                    result[igdb_id][store] = str(id_store)
        except Exception as e:
            logger.warning(f"Error getting all mappings: {e}")
        return result