import math

from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext


class MixedScore(GameScorer):
    def __init__(
        self,
        weight_critics: float = 0.3,
        weight_users: float = 0.5,
        weight_duration: float = 0.2,
        duration_scale: float = 80.0,
    ):
        total = weight_critics + weight_users + weight_duration
        assert abs(total - 1.0) < 1e-6

        self.weight_critics = weight_critics
        self.weight_users = weight_users
        self.weight_duration = weight_duration
        self.duration_scale = duration_scale

    def score(self, game: Game, ctx: ScoringContext) -> float:
        critics = game.critic_score or 0.0          # 0–100
        users = game.user_score or 0.0              # 0–100

        if game.duration_hours is not None:
            duration_norm = math.exp(-game.duration_hours / self.duration_scale) * 100
        else:
            duration_norm = 50.0  # neutral si desconocida

        return (
            critics * self.weight_critics +
            users * self.weight_users +
            duration_norm * self.weight_duration
        )
