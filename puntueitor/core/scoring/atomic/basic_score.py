from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext
from puntueitor.core.scoring.helpers import score_or_steam


class BasicScoreScorer(GameScorer):
    """
    Scoring simple: media de critic_score y user_score.
    Rango [0.0, 1.0].
    """
    def score(self, game: Game, ctx: ScoringContext) -> float:
        c = score_or_steam(game.critic_score, game.steam_score)
        u = score_or_steam(game.user_score, game.steam_score)
        return (c + u) / 2.0
