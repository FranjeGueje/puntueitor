from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from puntueitor.core.models import Game, ScoringContext, SelectionContext, Library


# Los cuerpos lanzan NotImplementedError en vez de ser `...`.
#
# El código del proyecto hereda de estos Protocol además de satisfacerlos
# estructuralmente. Con un cuerpo `...`, una clase que olvidara implementar su
# método heredaba ese cuerpo y devolvía None en silencio: así pasó
# desapercibido un GenreFilter que aceptaba todos los juegos. Ahora falla en
# voz alta, sin perder el tipado estructural para quien no herede.


class GameFilter(Protocol):
    """
    Pure predicate over a Game.
    """

    def matches(self, game: Game) -> bool:
        raise NotImplementedError


class GameScorer(Protocol):
    """
    Computes a numeric score for a Game given a scoring context.
    Must not mutate the Game or depend on ScoredGame.
    """

    def score(self, game: Game, ctx: ScoringContext) -> float:
        raise NotImplementedError


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
        raise NotImplementedError


@runtime_checkable
class GameEnricher(Protocol):
    def enrich(self, game: Game) -> Game:
        """
        Enriches a Game with additional data.
        Must never raise and must never create a new identity.
        """
        raise NotImplementedError


class GameSorter(Protocol):
    def sort(
        self,
        library: Library
    ) -> Library:
        """
        Returns a sorted library.
        Must never raise.
        """
        raise NotImplementedError
