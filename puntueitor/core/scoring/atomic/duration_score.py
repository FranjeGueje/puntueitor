from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext

class DurationScoreScorer(GameScorer):
    def score(self, game: Game, ctx: ScoringContext) -> float:
        if game.duration_hours is None:
            return 0.0

        h = game.duration_hours
        ideal = ctx.ideal_duration
        max_h = ctx.max_duration

        if h <= ideal:
            return 1.0

        if h >= max_h:
            return 0.0

        # caída lineal
        return 1.0 - (h - ideal) / (max_h - ideal)
