from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext


class AvailableTimeScorer(GameScorer):
    """
    Scores games based on how well they fit into the user's available time.
    Shorter than available time => positive score
    Longer => penalty
    """

    def score(self, game: Game, ctx: ScoringContext) -> float:
        # Si no hay contexto o duración, no influye
        if ctx.available_hours is None or ctx.available_hours <= 0:
            return 0.0

        if game.duration_hours is None:
            return 0.0

        available = ctx.available_hours
        duration = game.duration_hours

        # Encaja perfectamente
        if duration <= available:
            # Normalizamos entre 0 y 1
            return 1.0 - (duration / available) * 0.5

        # Se pasa de tiempo → penalización
        excess_ratio = (duration - available) / available
        return -min(excess_ratio, 1.0)
