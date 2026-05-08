import sqlite3
from pathlib import Path

class ExtrasCacher:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS extras (
                    id_igdb INTEGER PRIMARY KEY,
                    duration_hours REAL
                )
            """)
            conn.commit()

    def get_extras(self, igdb_id: int) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM extras WHERE id_igdb = ?", (igdb_id,))
            row = cursor.fetchone()
            return dict(row) if row else {}

    def save_extras(self, igdb_id: int, duration_hours: float | None) -> None:
        if duration_hours is None:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO extras (id_igdb, duration_hours)
                VALUES (?, ?)
                ON CONFLICT(id_igdb) DO UPDATE SET
                    duration_hours=excluded.duration_hours
            """, (igdb_id, duration_hours))
            conn.commit()
