from puntueitor.core.models import Game
from puntueitor.core.protocols import GameFilter


class FavoriteFilter(GameFilter):
    def __init__(self, favorite: bool):
        self.favorite = favorite

    def matches(self, game: Game) -> bool:
        return game.favorite == self.favorite
