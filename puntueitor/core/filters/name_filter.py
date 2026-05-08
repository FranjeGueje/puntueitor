from puntueitor.core.protocols import GameFilter
from puntueitor.core import Game
from puntueitor.core.models.util import normalize_title, similarity


class NameFilter(GameFilter):
    """
    Filtro de juegos por nombre usando LibraryIndex.
    - Busca coincidencias exactas y aproximadas.
    """

    def __init__(
        self,
        title: str,
        similarity_thrd: float = 0.8,
    ):
        self.normalized_query = normalize_title(title)
        self.similarity_thrd = similarity_thrd        


    def matches(self, game: Game) -> bool:
        # Fuzzy match usando similarity
        score = similarity(self.normalized_query, game.title_normalized)

        if score >= self.similarity_thrd:
            return True
        
        return False
