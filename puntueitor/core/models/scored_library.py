from __future__ import annotations
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
        # Los juegos sin puntuación van al final en ambos sentidos. Colarlos
        # con un ±inf solo funcionaba en uno de los dos: con +inf encabezaban
        # el ranking al ordenar de mayor a menor.
        scored = [sg for sg in self.scored_games if sg.score is not None]
        unscored = [sg for sg in self.scored_games if sg.score is None]

        scored.sort(key=lambda sg: sg.score, reverse=not ascending)

        return ScoredLibrary(scored_games=tuple(scored + unscored))

    