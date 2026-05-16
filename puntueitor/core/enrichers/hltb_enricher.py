from abc import ABC, abstractmethod
from dataclasses import replace

from puntueitor.core.protocols import GameEnricher
from puntueitor.core import Game
from puntueitor.core.raw.howlongtobeat.hltb_entry import HLTBEntry


import logging

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
    def __init__(
        self,
        client: HLTBClient,
        min_similarity: float = 0.6,
        overwrite: bool = False,
    ):
        assert 0.0 <= min_similarity <= 1.0
        self.client = client
        self.min_similarity = min_similarity
        self.overwrite = overwrite


    def enrich(self, game: Game) -> Game:
        if game.duration_hours is not None and not self.overwrite:
            return game

        try:
            entry = self.client.search(game.title)
        except Exception as e:
            logger.error(f"Error searching HLTB for {game.title}: {e}")
            return game

        if not entry:
            logger.debug(f"No HLTB entry found for {game.title}")
            return replace(game, duration_hours=0)

        if entry.similarity < self.min_similarity:
            logger.debug(f"HLTB similarity too low for {game.title}: {entry.similarity} < {self.min_similarity}")
            return replace(game, duration_hours=0)

        # Priorizar main_story, luego main_extra
        duration = entry.main_story if entry.main_story else entry.main_extra
        
        if duration is None or duration <= 0:
            logger.debug(f"HLTB duration not found for {game.title}")
            return replace(game, duration_hours=0)

        logger.info(f"Enriched {game.title} with {duration}h from HLTB")
        return replace(game, duration_hours=duration)
