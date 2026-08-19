from collections.abc import Iterable

from puntueitor.core import Library, Game
from puntueitor.core.models import Stores


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





def active_stores(config=None) -> set[Stores]:
    """
    Las tiendas marcadas en la configuración ("TIENDAS A CARGAR").

    Deciden dos cosas distintas y las dos importan: de qué tiendas se escanea
    (`pipeline.load_library.load_library`) y qué juegos se enseñan.
    """
    if config is None:
        from puntueitor.core.config import ConfigManager

        config = ConfigManager().get
    from puntueitor.core import stores

    return {spec.store for spec in stores.active(config)}


def is_in_active_stores(game: Game, active: set[Stores]) -> bool:
    """
    ¿Se enseña este juego con esas tiendas marcadas?

    Basta con que UNA de sus tiendas lo esté: un juego que tienes en Steam y
    en Epic lo sigues teniendo aunque desmarques una de las dos.

    Un juego sin ninguna tienda conocida se enseña siempre: no pertenece a
    ninguna de las desmarcadas, así que esconderlo sería inventarse un
    criterio que el usuario no ha pedido.
    """
    if game is None or not game.stores:
        return True
    return any(store in active for store in game.stores)
