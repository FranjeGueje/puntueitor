import logging
from pathlib import Path

from puntueitor.core.cachers.base_cacher import BaseCacher
from puntueitor.core import paths

logger = logging.getLogger(__name__)

_FLAGS = ("finished", "hidden", "backlog", "favorite")


class LibraryCacher(BaseCacher):
    """
    Estados editables del usuario, separados de la caché de red.

    Vive en ~/.local/share (datos del usuario, no regenerables) y no en ~/.cache,
    para que borrar la caché nunca pierda las marcas de terminado/favorito.
    """

    @staticmethod
    def default_path() -> Path:
        return paths.library_db()

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS user_games (
            igdb_id INTEGER PRIMARY KEY,
            finished INTEGER NOT NULL DEFAULT 0,
            hidden INTEGER NOT NULL DEFAULT 0,
            backlog INTEGER NOT NULL DEFAULT 0,
            favorite INTEGER NOT NULL DEFAULT 0
        );
    """

    @staticmethod
    def _row_to_status(row) -> dict:
        return {flag: bool(row[flag]) for flag in _FLAGS}

    def get_status(self, igdb_id: int) -> dict:
        rows = self._query("SELECT * FROM user_games WHERE igdb_id = ?", (igdb_id,))
        return self._row_to_status(rows[0]) if rows else {}

    def set_status(
        self,
        igdb_id: int,
        finished: bool = False,
        hidden: bool = False,
        backlog: bool = False,
        favorite: bool = False,
    ) -> None:
        self._write("""
            INSERT INTO user_games (igdb_id, finished, hidden, backlog, favorite)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(igdb_id) DO UPDATE SET
                finished = excluded.finished,
                hidden = excluded.hidden,
                backlog = excluded.backlog,
                favorite = excluded.favorite
        """, (igdb_id, int(finished), int(hidden), int(backlog), int(favorite)))

    def get_all_statuses(self) -> dict[int, dict]:
        return {
            row["igdb_id"]: self._row_to_status(row)
            for row in self._query("SELECT * FROM user_games")
        }
