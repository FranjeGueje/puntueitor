from collections.abc import Iterable

from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext


def _lowered(genres: Iterable[str] | None) -> set[str]:
    return {g.lower() for g in genres} if genres else set()


class GenreScorer(GameScorer):
    """
    Puntúa un juego basándose en los géneros preferidos y odiados del contexto.
    - Género preferido: +1.0 (normalizado por cantidad de géneros del juego)
    - Género odiado: -1.0
    - Sin info: 0.0
    """

    def score(self, game: Game, ctx: ScoringContext) -> float:
        if not game.genres:
            return 0.0

        # Los conjuntos se normalizan una vez por juego; antes se reconstruían
        # dentro de la comprensión, o sea una vez por género de cada juego.
        preferred = _lowered(ctx.preferred_genres)
        disliked = _lowered(ctx.disliked_genres)
        if not preferred and not disliked:
            return 0.0

        genres = [g.lower() for g in game.genres]
        total = len(genres)

        score = 0.0
        if preferred:
            score += sum(1 for g in genres if g in preferred) / total
        if disliked:
            score -= sum(1 for g in genres if g in disliked) / total

        return max(-1.0, min(1.0, score))
