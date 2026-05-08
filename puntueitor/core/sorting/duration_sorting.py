from puntueitor.core.protocols import GameSorter
from puntueitor.core import Library


class DurationSorter(GameSorter):
    def __init__(self, ascending: bool = True):
        self.ascending = ascending

    def sort(
        self,
        library: Library
    ) -> Library:
        games = library.games
        games_sorted = sorted(
            games,
            key=lambda g: g.duration_hours if g.duration_hours not in (None, 0.0) else float("inf"),
            reverse=not self.ascending,
        )
        return Library(games=tuple(games_sorted))
