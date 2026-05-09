import math

from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext


class MixedScore(GameScorer):
    def __init__(
        self,
        weight_critics: float = 0.3,
        weight_users: float = 0.5,
        weight_duration: float = 0.2,
    ):
        total = weight_critics + weight_users + weight_duration
        assert abs(total - 1.0) < 1e-6

        self.weight_critics = weight_critics
        self.weight_users = weight_users
        self.weight_duration = weight_duration

    def score(self, game: Game, ctx: ScoringContext) -> float:
        # Normalizamos a 0-1 (IGDB usa 0-100)
        critics = (game.critic_score or 0.0) / 100.0
        users = (game.user_score or 0.0) / 100.0

        if game.duration_hours is not None:
            # math.exp(-x) ya está en el rango (0, 1]
            duration_norm = math.exp(-game.duration_hours / ctx.duration_scale)
        else:
            duration_norm = ctx.neutral_duration_score

        return (
            critics * self.weight_critics +
            users * self.weight_users +
            duration_norm * self.weight_duration
        )
