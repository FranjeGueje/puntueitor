from puntueitor.core import Library, Game


def add_game(library: Library, game: Game) -> Library:
    """
    Returns a new Library with the game added if not already present.
    Identity is preserved by igdb_id.
    """
    if library.contains_igdb_id(game.igdb_id):
        return library

    return Library.from_iterable((*library.games, game))


def add_games(library: Library, games: list[Game]) -> Library:
    current = library
    for g in games:
        current = add_game(current, g)
    return current
