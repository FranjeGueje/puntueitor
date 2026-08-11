import logging

from puntueitor.core.cachers.base_cacher import BaseCacher

logger = logging.getLogger(__name__)


class DesconocidosCacher(BaseCacher):
    """Juegos que no se han podido resolver contra IGDB."""

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS unknown_games (
            store TEXT NOT NULL,
            title TEXT NOT NULL,
            id TEXT NOT NULL,
            UNIQUE(store, id)
        );
    """

    def save_unknown(self, store: str, title: str, game_id: str) -> None:
        self._write(
            "INSERT OR IGNORE INTO unknown_games (store, title, id) VALUES (?, ?, ?)",
            (store, title, str(game_id)),
        )

    def is_unknown(self, store: str, game_id: str) -> bool:
        return bool(self._query(
            "SELECT 1 FROM unknown_games WHERE store = ? AND id = ?",
            (store, str(game_id)),
        ))

    def get_all(self) -> list[dict]:
        return [dict(row) for row in self._query("SELECT * FROM unknown_games")]

    def get_by_store(self, store: str) -> list[dict]:
        return [
            dict(row)
            for row in self._query(
                "SELECT * FROM unknown_games WHERE store = ?", (store,)
            )
        ]

    def count(self) -> int:
        rows = self._query("SELECT COUNT(*) FROM unknown_games")
        return rows[0][0] if rows else 0

    def remove_unknown(self, store: str, game_id: str) -> None:
        self._write(
            "DELETE FROM unknown_games WHERE store = ? AND id = ?",
            (store, str(game_id)),
        )

    def clear(self) -> None:
        self._write("DELETE FROM unknown_games")
