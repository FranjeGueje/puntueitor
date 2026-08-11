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

        def rating_or_none(score: float | None) -> float | None:
            return score if score not in (None, 0.0) else None

        def key(g):
            user = rating_or_none(g.user_score)
            critic = rating_or_none(g.critic_score)
            if user is not None and critic is not None:
                return (user + critic) / 2
            if user is not None:
                return user
            if critic is not None:
                return critic
            return float("-inf")

        games_sorted = sorted(games, key=key, reverse=not self.ascending)
        return Library(games=tuple(games_sorted))