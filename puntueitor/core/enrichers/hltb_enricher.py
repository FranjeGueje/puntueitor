from abc import ABC, abstractmethod
from dataclasses import replace

from puntueitor.core.protocols import GameEnricher
from puntueitor.core import Game
from puntueitor.core.raw.howlongtobeat.hltb_entry import HLTBEntry


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
        min_similarity: float = 0.7,
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
        except Exception:
            return game

        if (
            not entry
            or entry.similarity < self.min_similarity
            or entry.main_story is None
        ):
            return game

        return replace(game, duration_hours=entry.main_extra)
