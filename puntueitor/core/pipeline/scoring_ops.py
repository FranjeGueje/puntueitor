from collections.abc import Sequence

from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, Library, ScoredGame, ScoredLibrary, ScoringContext

def score_game(
    game: Game,
    scorer: GameScorer,
    ctx: ScoringContext,
) -> ScoredGame:
    return ScoredGame(game, score=scorer.score(game=game, ctx=ctx))

def score_library(
    library: Library,
    scorer: GameScorer,
    ctx: ScoringContext,
) -> ScoredLibrary:
    returned_list: list[ScoredGame] = []
    for game in library.games:
        if game.duration_hours is not None and game.duration_hours == 0.0:
            returned_list.append(ScoredGame(game, score=0.0))
        else:
            returned_list.append(
                ScoredGame(game, score=scorer.score(game=game, ctx=ctx))
            )
    
    returned_scored_list = ScoredLibrary(returned_list)
    return returned_scored_list.sort()
    