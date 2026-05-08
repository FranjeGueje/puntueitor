from typing import Sequence
from puntueitor.core.protocols import GameFilter
from puntueitor.core.models.library import Library

from puntueitor.core.services.library_ops import add_game


def filter_library(
    library: Library,
    filter: GameFilter,
) -> Library:
    
    library_returned = Library.from_iterable(())
    for game in library.games:
        if filter.matches(game):
            library_returned = add_game(library_returned, game)
    
    return library_returned


def or_filter_library(
    library: Library,
    filters: Sequence[GameFilter],
) -> Library:
    
    library_returned = Library.from_iterable(())
    for game in library.games:
        for filter in filters:
            if filter.matches(game):
                library_returned = add_game(library_returned, game)
                break
    
    return library_returned


def and_filter_library(
    library: Library,
    filters: Sequence[GameFilter],
) -> Library:
    
    library_returned = Library.from_iterable(())
    for game in library.games:
        if all(f.matches(game) for f in filters):
            library_returned = add_game(library_returned, game)

    
    return library_returned