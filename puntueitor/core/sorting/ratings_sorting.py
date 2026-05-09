from puntueitor.core.protocols import GameSorter
from puntueitor.core import Library


class CriticRatingSorter(GameSorter):
    def __init__(self, ascending: bool = False):
        self.ascending = ascending

    def sort(
        self,
        library: Library
    ) -> Library:
        games = library.games
        games_sorted = sorted(
            games,
            key=lambda g: g.critic_score if g.critic_score not in (None, 0.0) else float("-inf"),
            reverse=not self.ascending,
        )
        return Library(games=tuple(games_sorted))


class UserRatingSorter(GameSorter):
    def __init__(self, ascending: bool = False):
        self.ascending = ascending

    def sort(
        self,
        library: Library
    ) -> Library:
        games = library.games
        games_sorted = sorted(
            games,
            key=lambda g: g.user_score if g.user_score not in (None, 0.0) else float("-inf"),
            reverse=not self.ascending,
        )
        return Library(games=tuple(games_sorted))

class TotalRatingSorter(GameSorter):
    def __init__(self, ascending: bool = False):
        self.ascending = ascending

    def sort(
        self,
        library: Library
    ) -> Library:
        games = library.games
        games_sorted = sorted(
            games,
            key=lambda g: (
                (g.user_score + g.critic_score) / 2 if g.user_score is not None and g.critic_score is not None
                else g.user_score if g.user_score is not None
                else g.critic_score if g.critic_score is not None
                else float("-inf")
            ),
            reverse=not self.ascending,
        )
        return Library(games=tuple(games_sorted))