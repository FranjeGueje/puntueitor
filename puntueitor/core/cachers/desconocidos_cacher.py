import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class DesconocidosCacher:
    """Caché para juegos no encontrados en IGDB."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path.home() / ".cache" / "puntueitor" / "desconocidos.sqlite"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS unknown_games (
                    store TEXT NOT NULL,
                    title TEXT NOT NULL,
                    id TEXT NOT NULL,
                    UNIQUE(store, id)
                )
            """)
            conn.commit()

    def save_unknown(self, store: str, title: str, game_id: str) -> None:
        """Guarda un juego no encontrado en IGDB."""
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO unknown_games (store, title, id)
                    VALUES (?, ?, ?)
                """, (store, title, game_id))
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to save unknown game {store}/{game_id}: {e}")

    def is_unknown(self, store: str, game_id: str) -> bool:
        """Verifica si un juego ya está en la lista de desconocidos."""
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM unknown_games WHERE store = ? AND id = ?",
                (store, game_id)
            )
            return cursor.fetchone() is not None

    def get_all(self) -> list[dict]:
        """Obtiene todos los juegos desconocidos."""
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM unknown_games")
            return [dict(row) for row in cursor.fetchall()]

    def get_by_store(self, store: str) -> list[dict]:
        """Obtiene juegos desconocidos de una tienda específica."""
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM unknown_games WHERE store = ?",
                (store,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def count(self) -> int:
        """Cuenta el total de juegos desconocidos."""
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM unknown_games")
            return cursor.fetchone()[0]

    def clear(self) -> None:
        """Borra todos los juegos desconocidos."""
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("DELETE FROM unknown_games")
            conn.commit()