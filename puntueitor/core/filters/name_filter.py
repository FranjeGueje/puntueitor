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
        # 1. Búsqueda por subcadena (más intuitiva)
        if self.normalized_query in game.title_normalized:
            return True
        
        # 2. Búsqueda por subcadena en el título original (por si acaso)
        if self.normalized_query in game.title.lower():
            return True

        # 3. Fuzzy match usando similarity para errores tipográficos
        score = similarity(self.normalized_query, game.title_normalized)
        return score >= self.similarity_thrd
