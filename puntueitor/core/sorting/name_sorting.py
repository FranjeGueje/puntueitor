from puntueitor.core.protocols import GameSorter
from puntueitor.core import Library


class NameSorter(GameSorter):
    def __init__(self, ascending: bool = True):
        self.ascending = ascending

    def sort(
        self,
        library: Library
    ) -> Library:
        games = library.games
        games_sorted = sorted(
            games,
            key=lambda g: g.title.lower(),
            reverse=not self.ascending,
        )
        return Library(games=tuple(games_sorted))

