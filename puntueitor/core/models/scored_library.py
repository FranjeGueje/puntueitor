from dataclasses import dataclass
from collections.abc import Iterable, Iterator

from .scored_game import ScoredGame


@dataclass(frozen=True)
class ScoredLibrary:
    scored_games: tuple[ScoredGame, ...]

    @classmethod
    def from_iterable(cls, scored_games: Iterable[ScoredGame]) -> ScoredLibrary:
        return cls(tuple(scored_games))

    def __iter__(self) -> Iterator[ScoredGame]:
        return iter(self.scored_games)

    def __len__(self) -> int:
        return len(self.scored_games)
    
    def sort(
        self,
        ascending: bool = False,
    ) -> ScoredLibrary:
        games = self.scored_games
        games_sorted = sorted(
            games,
            key=lambda g: g.score if g.score is not None else float("inf"),
            reverse=not ascending,
        )
        return ScoredLibrary(scored_games=tuple(games_sorted))

    