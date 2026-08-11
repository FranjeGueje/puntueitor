from puntueitor.core.protocols import GameSorter
from puntueitor.core import Library
from puntueitor.core.models.util import is_missing

# Las puntuaciones ausentes van siempre al final, tanto en orden ascendente
# como descendente.
MISSING = float("-inf")


class CriticRatingSorter(GameSorter):
    def __init__(self, ascending: bool = False):
        self.ascending = ascending

    def sort(self, library: Library) -> Library:
        games_sorted = sorted(
            library.games,
            key=lambda g: MISSING if is_missing(g.critic_score) else g.critic_score,
            reverse=not self.ascending,
        )
        return Library(games=tuple(games_sorted))


class UserRatingSorter(GameSorter):
    def __init__(self, ascending: bool = False):
        self.ascending = ascending

    def sort(self, library: Library) -> Library:
        games_sorted = sorted(
            library.games,
            key=lambda g: MISSING if is_missing(g.user_score) else g.user_score,
            reverse=not self.ascending,
        )
        return Library(games=tuple(games_sorted))


class TotalRatingSorter(GameSorter):
    def __init__(self, ascending: bool = False):
        self.ascending = ascending

    @staticmethod
    def _average(game) -> float:
        """Media de las puntuaciones disponibles, o MISSING si no hay ninguna."""
        scores = [
            score
            for score in (game.user_score, game.critic_score)
            if not is_missing(score)
        ]
        return sum(scores) / len(scores) if scores else MISSING

    def sort(self, library: Library) -> Library:
        games_sorted = sorted(
            library.games,
            key=self._average,
            reverse=not self.ascending,
        )
        return Library(games=tuple(games_sorted))
