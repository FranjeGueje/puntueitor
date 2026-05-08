from collections.abc import Sequence

from puntueitor.core.models import Game, ScoringContext
from puntueitor.core.protocols import GameScorer


class CompositeGameScorer:
    """
    Combines multiple GameScorers into a single weighted score.

    This class does NOT score by itself; it delegates to its components.
    """

    def __init__(self, scorers: Sequence[tuple[GameScorer, float]]) -> None:
        self._scorers = scorers

    def score(self, game: Game, ctx: ScoringContext) -> float:
        return sum(
            scorer.score(game, ctx) * weight
            for scorer, weight in self._scorers
        )
