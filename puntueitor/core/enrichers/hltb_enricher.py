import logging
from abc import ABC, abstractmethod
from dataclasses import replace

from puntueitor.core.cachers.extras_cacher import ExtrasCacher
from puntueitor.core.protocols import GameEnricher
from puntueitor.core import Game
from puntueitor.core.raw.howlongtobeat.hltb_entry import HLTBEntry

logger = logging.getLogger(__name__)


class HLTBClient(ABC):
    """
    Thin wrapper over howlongtobeat API / library.
    Returns raw HLTBEntry objects.
    """

    @abstractmethod
    def search(self, title: str) -> HLTBEntry | None:
        ...


class HLTBEnricher(GameEnricher):
    """
    Añade la duración estimada de HowLongToBeat.

    Cuando no encuentra el juego deja `duration_hours` en None ("desconocido")
    y lo anota en `extras.hltb_checked` para no repetir la búsqueda en cada
    arranque. Antes escribía 0, que los scorers interpretaban como una duración
    real de cero horas y colocaba esos juegos en lo más alto del ranking.
    """

    def __init__(
        self,
        client: HLTBClient,
        min_similarity: float = 0.6,
        overwrite: bool = False,
        extras_cacher: ExtrasCacher | None = None,
    ):
        assert 0.0 <= min_similarity <= 1.0
        self.client = client
        self.min_similarity = min_similarity
        self.overwrite = overwrite
        self.extras_cacher = extras_cacher

    def _mark_checked(self, game: Game) -> None:
        if self.extras_cacher is not None:
            self.extras_cacher.mark_hltb_checked(game.igdb_id)

    def enrich(self, game: Game) -> Game:
        if not self.overwrite:
            if game.duration_hours is not None:
                return game
            if self.extras_cacher and self.extras_cacher.is_hltb_checked(game.igdb_id):
                logger.debug(f"HLTB already checked without result for {game.title}")
                return game

        try:
            entry = self.client.search(game.title)
        except Exception as e:
            # Fallo transitorio: no lo marcamos como comprobado para poder
            # reintentar en la siguiente pasada.
            logger.error(f"Error searching HLTB for {game.title}: {e}")
            return game

        if not entry:
            logger.debug(f"No HLTB entry found for {game.title}")
            self._mark_checked(game)
            return game

        if entry.similarity < self.min_similarity:
            logger.debug(
                f"HLTB similarity too low for {game.title}: "
                f"{entry.similarity} < {self.min_similarity}"
            )
            self._mark_checked(game)
            return game

        # Priorizar main_story, luego main_extra
        duration = entry.main_story if entry.main_story else entry.main_extra

        if duration is None or duration <= 0:
            logger.debug(f"HLTB duration not found for {game.title}")
            self._mark_checked(game)
            return game

        logger.info(f"Enriched {game.title} with {duration}h from HLTB")
        return replace(game, duration_hours=duration)
