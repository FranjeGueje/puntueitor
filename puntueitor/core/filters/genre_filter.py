from collections.abc import Iterable

from puntueitor.core.protocols import GameFilter
from puntueitor.core import Game


class GenreFilter(GameFilter):
    def __init__(self, genres: Iterable[str]) -> None:
        self.genres = {g.lower() for g in genres}

    def matches(self, game: Game) -> bool:
        if not self.genres:
            return True
        return any(g.lower() in self.genres for g in game.genres)
