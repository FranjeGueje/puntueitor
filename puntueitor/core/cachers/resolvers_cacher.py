import sqlite3
from pathlib import Path
from typing import Sequence

class ResolversCacher:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id_igdb FROM resolvers WHERE store = ? AND id_store = ?",
                (store, str(id_store))
            )
            rows = cursor.fetchall()
            if rows:
                return [row[0] for row in rows]
            return None

    def set_igdb_ids(self, store: str, id_store: str, igdb_ids: Sequence[int]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            # Delete old mappings for this store+id just in case
            conn.execute(
                "DELETE FROM resolvers WHERE store = ? AND id_store = ?",
                (store, str(id_store))
            )
            
            # Insert new mappings
            conn.executemany(
                "INSERT INTO resolvers (store, id_store, id_igdb) VALUES (?, ?, ?)",
                [(store, str(id_store), igdb_id) for igdb_id in igdb_ids]
            )
            conn.commit()
