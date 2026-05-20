from puntueitor.core.models import Game
from puntueitor.core.protocols import GameFilter


class HiddenFilter(GameFilter):
    def __init__(self, hidden: bool):
        self.hidden = hidden

    def matches(self, game: Game) -> bool:
        return game.hidden == self.hidden
