from puntueitor.core.protocols import GameFilter
from puntueitor.core import Game


class GenreFilter(GameFilter):
    def matches(self, game: Game) -> bool:
        return True
