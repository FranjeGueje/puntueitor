import json
import logging
import time
from pathlib import Path

from puntueitor.core.cachers.base_cacher import BaseCacher
from puntueitor.core import paths

logger = logging.getLogger(__name__)

_INSERT = """
    INSERT OR REPLACE INTO store_games (store, store_id, title, raw, fetched_at)
    VALUES (:store, :store_id, :title, :raw, :fetched_at)
"""


class StoreLibraryCacher(BaseCacher):
    """
    La última biblioteca que cada tienda nos devolvió por su API.

    Es lo que permite arrancar sin conexión: los proveedores llaman a la web
    cuando toca refrescar y, si no hay red o la sesión ha caducado, se sirven
    de aquí en vez de dejar la tienda vacía. Guardamos el JSON crudo tal cual
    llegó porque quien lo consume son los resolvers, y lo que necesitan es el
    diccionario de la tienda entero, no los tres campos que hoy sabemos leer.

    Una sola base para las cuatro tiendas, con `store` en la clave: son datos
    del mismo tipo y con el mismo ciclo de vida, y así vaciar una tienda o
    contarlas todas es una consulta, no un recorrido de ficheros.
    """

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS store_games (
            store      TEXT NOT NULL,
            store_id   TEXT NOT NULL,
            title      TEXT,
            raw        JSON NOT NULL,
            fetched_at INTEGER NOT NULL,
            PRIMARY KEY (store, store_id)
        );
    """

    @staticmethod
    def default_path() -> Path:
        # Caché de verdad: es una copia de lo que sirve la tienda y se rehace
        # sola con un refresco, así que va a ~/.cache y no a ~/.local/share.
        return paths.store_libraries_db()

    def __init__(self, store: str, db_path: str | Path | None = None):
        self.store = str(store)
        super().__init__(db_path)

    def get_games(self) -> list[dict] | None:
        """
        Los crudos guardados de esta tienda, o None si no hay ninguno.

        None y lista vacía significan cosas distintas y quien llama las
        distingue: None es «nunca se ha llegado a bajar esta tienda» y la
        lista vacía sería «la tienda contestó que no tienes nada». Por eso no
        se colapsan en un solo valor falsy.
        """
        rows = self._query(
            "SELECT raw FROM store_games WHERE store = ?", (self.store,),
        )
        if not rows:
            return None

        games = []
        for row in rows:
            try:
                games.append(json.loads(row["raw"]))
            except (json.JSONDecodeError, TypeError) as error:
                # Una fila ilegible no puede tirar la biblioteca entera: se
                # pierde ese juego y el resto sigue.
                logger.warning(f"{self.store}: fila de caché ilegible: {error}")
        return games or None

    def title_of(self, store_id: str) -> str | None:
        """El nombre que tiene `store_id` en esta tienda, sin cargar el resto."""
        rows = self._query(
            "SELECT title FROM store_games WHERE store = ? AND store_id = ?",
            (self.store, str(store_id)),
        )
        return (rows[0]["title"] or None) if rows else None

    def fetched_at(self) -> int | None:
        """Cuándo se bajó esta tienda por última vez (epoch), o None."""
        rows = self._query(
            "SELECT MAX(fetched_at) AS ts FROM store_games WHERE store = ?",
            (self.store,),
        )
        return rows[0]["ts"] if rows and rows[0]["ts"] is not None else None

    def save_games(self, games: list[dict], id_of, title_of) -> None:
        """
        Reemplaza lo guardado de esta tienda por `games`.

        `id_of` y `title_of` los pone el proveedor: cada tienda llama de otra
        manera a su identificador (`appid`, `app_name`, `id`) y esa traducción
        es suya, no de la caché.

        Se borra y se inserta dentro de la MISMA transacción a propósito: si
        el proceso muere en medio, la caché se queda con la biblioteca
        anterior entera en vez de con media biblioteca nueva.
        """
        if not self._available:
            return

        now = int(time.time())
        rows = []
        for game in games:
            store_id = str(id_of(game) or "")
            if not store_id:
                logger.debug(f"{self.store}: juego sin identificador, se salta")
                continue
            rows.append({
                "store": self.store,
                "store_id": store_id,
                "title": title_of(game) or None,
                "raw": json.dumps(game, ensure_ascii=False),
                "fetched_at": now,
            })

        if not rows:
            logger.warning(
                f"{self.store}: ningún juego válido que guardar; se conserva "
                "la copia anterior"
            )
            return

        try:
            conn = self._connect()
            with conn:
                conn.execute("DELETE FROM store_games WHERE store = ?", (self.store,))
                conn.executemany(_INSERT, rows)
            logger.debug(f"{self.store}: {len(rows)} juegos guardados en caché")
        except Exception as error:
            logger.error(f"no se pudo guardar la caché de {self.store}: {error}")

    def clear(self) -> bool:
        """Olvida lo guardado de ESTA tienda; las demás se quedan como están."""
        return self._write(
            "DELETE FROM store_games WHERE store = ?", (self.store,),
        )
