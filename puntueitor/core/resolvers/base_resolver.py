from abc import ABC, abstractmethod
from collections.abc import Sequence

from puntueitor.core import Game

class BaseResolver(ABC):
    @abstractmethod
    def resolve(self, raw: dict, refresh: bool = False) -> Sequence[Game]:
        """
        Intenta resolver un objeto crudo de una fuente externa
        a un Game del dominio.
        """
        raise NotImplementedError

    