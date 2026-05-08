from collections import defaultdict

from puntueitor.core import Library, Game
from puntueitor.core.models.util import normalize_title, similarity


class LibraryIndex:
    """
    Read-only index over a Library.
    Can be rebuilt at any time.
    """

    def __init__(self, library: Library):
        self._library = library
        self._by_title: dict[str, list[Game]] = defaultdict(list)
        self._build()

    def _build(self) -> None:
        for game in self._library:
            self._by_title[game.title_normalized].append(game)

    def find_by_title(self, title: str) -> list[Game]:
        norm = normalize_title(title)
        return list(self._by_title.get(norm, []))

    def fuzzy_match_title(
        self,
        title: str,
        threshold: float = 0.75,
    ) -> list[tuple[Game, float]]:
        norm = normalize_title(title)
        results: list[tuple[Game, float]] = []

        for games in self._by_title.values():
            for game in games:
                score = similarity(norm, game.title_normalized)
                if score >= threshold:
                    results.append((game, score))

        return sorted(results, key=lambda x: x[1], reverse=True)
