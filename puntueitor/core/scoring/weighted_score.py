from collections.abc import Sequence

from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext


class WeightedScore(GameScorer):
    def __init__(self, scorers: Sequence[tuple[GameScorer, float]]):
        self.scorers = scorers

    def score(self, game: Game, ctx: ScoringContext) -> float:
        total = 0.0
        for scorer, weight in self.scorers:
            try:
                total += scorer.score(game, ctx) * weight
            except Exception:
                continue
        return total
