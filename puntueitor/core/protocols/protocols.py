from collections.abc import Sequence
from typing import Protocol
from typing import runtime_checkable #Esto permite isinstance(enricher, GameEnricher) en tests o pipelines dinámicos.

from puntueitor.core.models import Game, ScoringContext, SelectionContext, Library


class GameFilter(Protocol):
    """
    Pure predicate over a Game.
    """

    def matches(self, game: Game) -> bool:
        ...


class GameScorer(Protocol):
    """
    Computes a numeric score for a Game given a selection context.
    Must not mutate the Game or depend on ScoredGame.
    """

    def score(self, game: Game, ctx: ScoringContext) -> float:
        ...


class GameSelector(Protocol):
    """
    Resolves identity ambiguity among candidate Games
    returned by an external source (e.g. IGDB).
    """

    def select(
        self,
        candidates: Sequence[Game],
        ctx: SelectionContext,
    ) -> Game | None:
        ...


@runtime_checkable
class GameEnricher(Protocol):
    def enrich(self, game: Game) -> Game:
        """
        Enriches a Game with additional data.
        Must never raise and must never create a new identity.
        """
        ...

class GameSorter(Protocol):
    def sort(
        self,
        library: Library
    ) -> Library:
        """
        Returns a sorted library.
        Must never raise.
        """
        ...
