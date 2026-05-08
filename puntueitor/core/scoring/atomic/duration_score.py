from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext

class DurationScoreScorer(GameScorer):
    def __init__(self, ideal_hours: float = 15.0, max_hours: float = 60.0):
        self.ideal = ideal_hours
        self.max = max_hours

    def score(self, game: Game, ctx: ScoringContext) -> float:
        if game.duration_hours is None:
            return 0.0

        h = game.duration_hours

        if h <= self.ideal:
            return 1.0

        if h >= self.max:
            return 0.0

        # caída lineal
        return 1.0 - (h - self.ideal) / (self.max - self.ideal)
