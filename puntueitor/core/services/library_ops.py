from collections.abc import Iterable

from puntueitor.core import Library, Game


def add_game(library: Library, game: Game) -> Library:
    """
    Devuelve una Library nueva con el juego añadido si no estaba ya.
    La identidad se preserva por igdb_id.
    """
    if library.contains_igdb_id(game.igdb_id):
        return library

    return Library.from_iterable((*library.games, game))


def add_games(library: Library, games: Iterable[Game]) -> Library:
    """
    Añade varios juegos de una vez.

    Encadenar `add_game` era cuadrático: cada llamada reconstruía la tupla
    entera y rescaneaba la biblioteca. Aquí se resuelve en una sola pasada.
    """
    known = {g.igdb_id for g in library.games}

    added: list[Game] = []
    for game in games:
        if game.igdb_id in known:
            continue
        known.add(game.igdb_id)
        added.append(game)

    if not added:
        return library

    return Library.from_iterable((*library.games, *added))
