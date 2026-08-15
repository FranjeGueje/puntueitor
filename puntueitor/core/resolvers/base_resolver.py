import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from puntueitor.core.cachers.desconocidos_cacher import DesconocidosCacher
from puntueitor.core.cachers.resolvers_cacher import ResolversCacher
from puntueitor.core.igdb import IGDBService
from puntueitor.core.mappers import IGMapperGame
from puntueitor.core.models import Game, Stores

logger = logging.getLogger(__name__)

MAX_SEARCH_LEN = 50
MIN_SEARCH_LEN = 2


class BaseResolver(ABC):
    """
    Plantilla común de resolución de una tienda contra IGDB.

    Las cuatro tiendas seguían el mismo flujo copiado línea a línea, y habían
    divergido en detalles (comprobar la caché, tratar resultados vacíos). Aquí
    el flujo vive una sola vez y cada tienda aporta únicamente lo suyo:
    su identificador y su estrategia de búsqueda.
    """

    #: Tienda que resuelve esta implementación.
    STORE: Stores

    def __init__(
        self,
        igdb: IGDBService,
        cache_file: str | Path | None = None,
    ):
        self.igdb = igdb
        self.cacher = ResolversCacher(cache_file) if cache_file else None
        self.unknown_cacher = DesconocidosCacher()

    # ──────────────────────────────
    # Ganchos por tienda
    # ──────────────────────────────

    def _extract_id(self, raw: dict) -> str:
        """Identificador del juego dentro de la tienda."""
        return str(raw.get("app_name") or raw.get("id") or "")

    @staticmethod
    def _extract_title(raw: dict) -> str:
        return raw.get("title") or raw.get("name") or ""

    @abstractmethod
    def _search(self, raw: dict, store_id: str, title: str) -> list[dict] | None:
        """
        Busca el juego en IGDB.

        Devuelve la lista de candidatos, `[]` si se buscó y no hay resultados
        (el juego se marcará como desconocido), o `None` para omitirlo sin
        marcarlo (datos de entrada inservibles).
        """

    # ──────────────────────────────
    # Helpers compartidos
    # ──────────────────────────────

    def _search_by_title(self, title: str, store_id: str, limit: int = 5) -> list[dict] | None:
        """Búsqueda de respaldo por título. None si el título no sirve."""
        cleaned = title.strip()
        if len(cleaned) < MIN_SEARCH_LEN:
            logger.warning(
                f"[{self.STORE}] no se puede buscar el id {store_id}: su "
                f"título no sirve ('{title}')"
            )
            return None

        logger.debug(f"[{self.STORE}] buscando '{cleaned}' por título (id {store_id})")
        return self.igdb.search_by_title(
            cleaned[:MAX_SEARCH_LEN], limit=limit, cache_results=True
        )

    # ──────────────────────────────
    # Flujo
    # ──────────────────────────────

    def resolve(self, raw: dict, refresh: bool = False) -> Sequence[Game]:
        store = str(self.STORE)
        store_id = self._extract_id(raw)
        title = self._extract_title(raw)

        if not store_id:
            logger.warning(f"[{store}] '{title}' no trae identificador; se omite")
            return []

        if self.unknown_cacher.is_unknown(store, store_id):
            logger.debug(f"[{store}] '{title}' ya estaba marcado como desconocido")
            return []

        igdb_ids: list[int] | None = None
        if not refresh and self.cacher:
            igdb_ids = self.cacher.get_igdb_ids(store, store_id)

        if not igdb_ids:
            if self.cacher and not self.cacher.available:
                logger.warning(
                    f"[{store}] '{title}' sin resolver: la base de datos de la "
                    "biblioteca no está disponible"
                )
                return []

            results = self._search(raw, store_id, title)
            if results is None:
                return []

            igdb_ids = [r["id"] for r in results if "id" in r]

            if igdb_ids:
                if self.cacher:
                    self.cacher.set_igdb_ids(store, store_id, igdb_ids)
            else:
                # A INFO y no a WARNING: que un juego no esté en IGDB es
                # normal (demos, herramientas, betas) y no hay nada que
                # arreglar — queda en Desconocidos para identificarlo a mano.
                # Los fallos de RED al buscar no llegan aquí: los lanza
                # `_search` como excepción y los cuenta el pipeline aparte, y
                # mezclarlos era lo que hacía que un corte de internet
                # pareciera "IGDB no conoce ninguno de tus juegos".
                logger.info(
                    f"[{store}] '{title}' (id {store_id}) no está en IGDB; "
                    "va a Desconocidos"
                )
                self.unknown_cacher.save_unknown(store, title, store_id)

        return self._build_games(igdb_ids, store_id, refresh)

    def _build_games(
        self, igdb_ids: Sequence[int], store_id: str, refresh: bool
    ) -> list[Game]:
        games: list[Game] = []
        for igdb_id in igdb_ids or ():
            try:
                raw_game = self.igdb.get_game(igdb_id=igdb_id, refresh=refresh)
            except Exception as e:
                from puntueitor.core.diagnostics import describe_error
                logger.warning(
                    f"[{self.STORE}] no se pudo traer de IGDB la ficha "
                    f"{igdb_id}: {describe_error(e, 'IGDB')}"
                )
                continue
            game = IGMapperGame.map_to_game(raw_game)
            game.set_store(self.STORE, store_id)
            games.append(game)
        return games
