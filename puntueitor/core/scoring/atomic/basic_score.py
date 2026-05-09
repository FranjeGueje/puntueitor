from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext

class BasicScoreScorer(GameScorer):
    """
    Scoring simple: media de critic_score y user_score.
    Rango [0.0, 1.0].
    """
    def score(self, game: Game, ctx: ScoringContext) -> float:
        c = (game.critic_score or 0.0) / 100.0
        u = (game.user_score or 0.0) / 100.0
        
        if game.critic_score is not None and game.user_score is not None:
            return (c + u) / 2.0
        if game.critic_score is not None:
            return c
        if game.user_score is not None:
            return u
        return 0.0
