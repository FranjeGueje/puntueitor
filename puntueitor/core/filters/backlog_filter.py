from puntueitor.core.models import Game
from puntueitor.core.protocols import GameFilter


class BacklogFilter(GameFilter):
    def __init__(self, backlog: bool):
        self.backlog = backlog

    def matches(self, game: Game) -> bool:
        return game.backlog == self.backlog
