from dataclasses import dataclass
from collections.abc import Iterable, Iterator

from .game import Game


@dataclass(frozen=True)
class Library:
    games: tuple[Game, ...]

    @classmethod
    def from_iterable(cls, games: Iterable[Game]) -> "Library":
        return cls(tuple(games))

    def __iter__(self) -> Iterator[Game]:
        return iter(self.games)

    def __len__(self) -> int:
        return len(self.games)

    def contains_igdb_id(self, igdb_id: int) -> bool:
        return any(g.igdb_id == igdb_id for g in self.games)
