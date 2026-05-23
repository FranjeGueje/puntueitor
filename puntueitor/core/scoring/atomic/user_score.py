from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext
from puntueitor.core.scoring.helpers import score_or_steam


class UserScoreScorer(GameScorer):
    def score(self, game: Game, ctx: ScoringContext) -> float:
        return score_or_steam(game.user_score, game.steamdb_score)
