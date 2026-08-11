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
    returned_list: list[ScoredGame] = [
        ScoredGame(game, score=scorer.score(game=game, ctx=ctx))
        for game in library.games
    ]

    returned_scored_list = ScoredLibrary(returned_list)
    return returned_scored_list.sort()
    