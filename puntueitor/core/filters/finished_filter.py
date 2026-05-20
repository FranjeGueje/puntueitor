from puntueitor.core.models import Game
from puntueitor.core.protocols import GameFilter


class FinishedFilter(GameFilter):
    def __init__(self, finished: bool):
        self.finished = finished

    def matches(self, game: Game) -> bool:
        return game.finished == self.finished
