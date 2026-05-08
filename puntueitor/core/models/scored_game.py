from dataclasses import dataclass
from .game import Game

@dataclass(frozen=True, slots=True)
class ScoredGame:
    game: Game
    score: float
