from abc import ABC, abstractmethod
from collections.abc import Sequence
from puntueitor.core.models import Game, SelectionContext


class GameSelector(ABC):
    """
    Selecciona un Game de entre los candidatos proporcionados.
    """

    @abstractmethod
    def select(
        self,
        candidates: Sequence[Game],
        ctx: SelectionContext,
    ) -> Game | None:
        """
        Selecciona el mejor candidato de todos los Game pasados
        """
        raise NotImplementedError


class SimpleSelector(GameSelector):
    """
    Selecciona el Game más inmediato de los candidatos proporcionado.
    """

    def select(
        self,
        candidates: Sequence[Game],
        ctx: SelectionContext,
    ) -> Game | None:
        """
        Devuelve el mejor Game o None si no hay candidatos.
        """
        if not candidates:
            return None

        # Heurística mínima inicial:
        # el primer candidato ya viene ordenado por relevancia
        return candidates[0]

