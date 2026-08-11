import logging
from collections.abc import Sequence

from puntueitor.core.cachers.base_cacher import BaseCacher
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)


class ResolversCacher(BaseCacher):
    """Correlación (tienda, id_en_tienda) → igdb_id."""

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS resolvers (
            store TEXT,
            id_store TEXT,
            id_igdb INTEGER,
            PRIMARY KEY (store, id_store, id_igdb)
        );
    """

    def get_igdb_ids(self, store: str, id_store: str) -> list[int] | None:
        rows = self._query(
            "SELECT id_igdb FROM resolvers WHERE store = ? AND id_store = ?",
            (store, str(id_store)),
        )
        return [row[0] for row in rows] if rows else None

    def set_igdb_ids(self, store: str, id_store: str, igdb_ids: Sequence[int]) -> None:
        if not self._available:
            return
        try:
            conn = self._connect()
            with conn:
                conn.execute(
                    "DELETE FROM resolvers WHERE store = ? AND id_store = ?",
                    (store, str(id_store)),
                )
                conn.executemany(
                    "INSERT INTO resolvers (store, id_store, id_igdb) VALUES (?, ?, ?)",
                    [(store, str(id_store), igdb_id) for igdb_id in igdb_ids],
                )
        except Exception as e:
            logger.warning(f"Error setting igdb ids for {store}/{id_store}: {e}")

    def get_all_mappings(self) -> dict[int, dict[Stores, str]]:
        """Devuelve {igdb_id: {Stores: id_store, ...}}"""
        result: dict[int, dict[Stores, str]] = {}
        for store_str, id_store, igdb_id in self._query(
            "SELECT store, id_store, id_igdb FROM resolvers"
        ):
            try:
                store = Stores(store_str)
            except ValueError:
                continue
            result.setdefault(igdb_id, {})[store] = str(id_store)
        return result

    def get_stores_for_igdb_id(self, igdb_id: int) -> dict[str, str] | None:
        rows = self._query(
            "SELECT store, id_store FROM resolvers WHERE id_igdb = ?", (igdb_id,)
        )
        return {store: id_store for store, id_store in rows} if rows else None

    def remove_igdb_id(self, igdb_id: int) -> None:
        self._write("DELETE FROM resolvers WHERE id_igdb = ?", (igdb_id,))
