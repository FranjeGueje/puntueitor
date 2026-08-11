from collections.abc import Callable, Sequence

from puntueitor.core.models import Game
from puntueitor.core.models.library import Library
from puntueitor.core.protocols import GameFilter


def _collect(library: Library, keep: Callable[[Game], bool]) -> Library:
    """
    Recorre la biblioteca una sola vez conservando los juegos que pasan el
    predicado, sin repetir igdb_id.

    La versión anterior acumulaba con `add_game`, que rescanea la biblioteca y
    reconstruye la tupla en cada juego: filtrar 2000 juegos costaba ~62 ms
    frente a los ~0.1 ms de una sola pasada.
    """
    seen: set[int] = set()
    kept: list[Game] = []

    for game in library.games:
        if game.igdb_id in seen or not keep(game):
            continue
        seen.add(game.igdb_id)
        kept.append(game)

    return Library.from_iterable(kept)


def filter_library(library: Library, filter: GameFilter) -> Library:
    return _collect(library, filter.matches)


def or_filter_library(library: Library, filters: Sequence[GameFilter]) -> Library:
    return _collect(library, lambda game: any(f.matches(game) for f in filters))


def and_filter_library(library: Library, filters: Sequence[GameFilter]) -> Library:
    return _collect(library, lambda game: all(f.matches(game) for f in filters))
