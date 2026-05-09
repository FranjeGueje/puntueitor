from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, ScoringContext

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
        
        score = 0.0
        
        # Preferidos
        if ctx.preferred_genres:
            matches = [g for g in game.genres if g.lower() in {p.lower() for p in ctx.preferred_genres}]
            if matches:
                # Si tiene géneros preferidos, subimos la nota
                score += len(matches) / len(game.genres)
        
        # Odiados
        if ctx.disliked_genres:
            hated = [g for g in game.genres if g.lower() in {d.lower() for d in ctx.disliked_genres}]
            if hated:
                # Si tiene géneros odiados, bajamos la nota drásticamente
                score -= len(hated) / len(game.genres)
                
        return max(-1.0, min(1.0, score))
