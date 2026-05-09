import logging
from collections.abc import Sequence

from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext


logger = logging.getLogger(__name__)


class WeightedScore(GameScorer):
    def __init__(self, scorers: Sequence[tuple[GameScorer, float]]):
        self.scorers = scorers

    def score(self, game: Game, ctx: ScoringContext) -> float:
        total = 0.0
        for scorer, weight in self.scorers:
            try:
                s = scorer.score(game, ctx)
                if s is not None and isinstance(s, (int, float)):
                    total += s * weight
            except (TypeError, ValueError, AttributeError) as e:
                logger.debug(f"Scorer {type(scorer).__name__} failed for {game.title}: {e}")
                continue
        return total
