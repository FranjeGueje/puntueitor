from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext

class UserScoreScorer(GameScorer):
    def score(self, game: Game, ctx: ScoringContext) -> float:
        if game.user_score is None:
            return 0.0
        return game.user_score / 100.0
