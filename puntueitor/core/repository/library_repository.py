import logging
from pathlib import Path

from puntueitor.core.cachers.base_cacher import CACHE_DB
from puntueitor.core.cachers.desconocidos_cacher import DesconocidosCacher
from puntueitor.core.cachers.extras_cacher import ExtrasCacher
from puntueitor.core.cachers.igdb_cacher import IGDBCacher
from puntueitor.core.cachers.library_cacher import LibraryCacher
from puntueitor.core.cachers.resolvers_cacher import ResolversCacher
from puntueitor.core.mappers import IGMapperGame
from puntueitor.core.models import Game, Library

logger = logging.getLogger(__name__)

_EXTRA_FIELDS = (
    "duration_hours", "steam_review", "steamdb_score", "review_pos", "review_neg",
)
_STATUS_FIELDS = ("finished", "hidden", "backlog", "favorite")


class LibraryRepository:
    """
    Repositorio para gestionar la persistencia de la biblioteca de juegos.
    Cumple la REGLA DE ORO: puntueitor.db (tabla games) solo contiene datos
    canónicos. La biblioteca se reconstruye uniendo tiendas, resolvers y extras.
    """

    def __init__(self, cache_dir: str | Path | None = None):
        self.cache_dir = Path(cache_dir).resolve() if cache_dir else CACHE_DB.parent
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        db_path = self.cache_dir / "puntueitor.db"
        self.igdb_cacher = IGDBCacher(db_path)
        self.extras_cacher = ExtrasCacher(db_path)
        self.resolvers_cacher = ResolversCacher(db_path)
        self.library_cacher = LibraryCacher()
        self.unknown_cacher = DesconocidosCacher()

    # ──────────────────────────────
    # Guardado
    # ──────────────────────────────

    @staticmethod
    def _extras_row(game: Game) -> tuple | None:
        """Fila de extras del juego, o None si no hay nada que guardar."""
        values = tuple(getattr(game, field) for field in _EXTRA_FIELDS)
        if all(value is None for value in values):
            return None
        return (game.igdb_id, *values)

    def save(self, library: Library) -> None:
        """
        Guarda los campos no canónicos (extras) de toda la biblioteca.

        Los datos canónicos y las relaciones ya se persisten durante el
        pipeline. Se hace en una sola transacción: antes se abría una conexión
        SQLite por juego.
        """
        rows = [row for row in map(self._extras_row, library) if row is not None]
        self.extras_cacher.save_extras_bulk(rows)

    def save_game(self, game: Game) -> None:
        """Persiste los extras de un solo juego."""
        row = self._extras_row(game)
        if row is not None:
            self.extras_cacher.save_extras(*row)

    # ──────────────────────────────
    # Carga
    # ──────────────────────────────

    def load(self) -> Library:
        """Reconstruye la biblioteca desde la tabla resolvers (autoritativa)."""
        all_mappings = self.resolvers_cacher.get_all_mappings()
        if not all_mappings:
            logger.info("No games in puntueitor.db resolvers table, library empty")
            return Library.from_iterable(())

        all_games = {g["id"]: g for g in self.igdb_cacher.get_all_games()}
        all_extras = self.extras_cacher.get_all_extras()
        all_statuses = self.library_cacher.get_all_statuses()

        logger.info(f"Loading {len(all_mappings)} games from resolvers table")

        games: list[Game] = []
        for igdb_id, stores in all_mappings.items():
            raw = all_games.get(igdb_id)
            if not raw:
                logger.warning(
                    f"Game {igdb_id} in resolvers but not in igdb cache, skipping"
                )
                continue
            if not raw.get("name"):
                logger.warning(f"Cached game {igdb_id} has no name, skipping")
                continue

            # Misma conversión que en la carga desde red (carátula, géneros,
            # fecha): la delegamos en el mapper en vez de duplicarla aquí.
            game = IGMapperGame.map_to_game(raw)
            game.stores = dict(stores)

            extras = all_extras.get(igdb_id, {})
            for field in _EXTRA_FIELDS:
                setattr(game, field, extras.get(field))

            status = all_statuses.get(igdb_id, {})
            for field in _STATUS_FIELDS:
                setattr(game, field, status.get(field, False))

            games.append(game)

        logger.info(f"Built {len(games)} games from cache")
        return Library.from_iterable(games)
