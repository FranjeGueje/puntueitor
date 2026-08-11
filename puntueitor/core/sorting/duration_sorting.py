from puntueitor.core.protocols import GameSorter
from puntueitor.core import Library


class DurationSorter(GameSorter):
    def __init__(self, ascending: bool = True):
        self.ascending = ascending

    def sort(
        self,
        library: Library
    ) -> Library:
        # Los juegos de duración desconocida se quedan al final en ambos
        # sentidos: separarlos es más claro que colarlos con un ±inf, que
        # los ponía en cabeza al ordenar de mayor a menor.
        known = [g for g in library.games if g.duration_hours is not None]
        unknown = [g for g in library.games if g.duration_hours is None]

        known.sort(key=lambda g: g.duration_hours, reverse=not self.ascending)

        return Library(games=tuple(known + unknown))
