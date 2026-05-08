from puntueitor.core.protocols import GameFilter
from puntueitor.core import Game


class DurationFilter(GameFilter):
    def __init__(self, hours: float) -> None:
        super().__init__()
        self.hours = hours

    def matches(self, game: Game) -> bool:
        return game.duration_hours <= self.hours if game.duration_hours else True
