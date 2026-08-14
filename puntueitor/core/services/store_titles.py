"""
Cómo se llama un juego EN SU TIENDA, no en IGDB.

Los dos nombres no son el mismo, y la diferencia importa al desconocer un
juego: se desconoce precisamente porque IGDB lo identificó mal, así que
apuntarlo en `unknown_games` con el nombre de IGDB borra la pista de qué juego
era de verdad. Con el de la tienda, la lista de desconocidos sigue diciendo lo
mismo que dice tu biblioteca de Steam o de Heroic, que es donde vas a mirar
para identificarlo a mano.

Es también el criterio que ya usa el escaneo: un desconocido que nace ahí se
apunta con `BaseResolver._extract_title(raw)`, o sea el título de la tienda.
Esto es lo que hace que las dos vías llenen la tabla igual.

No hace falta red ni volver a escanear: las mismas fuentes que lee el pipeline
están en disco.
"""
import logging

logger = logging.getLogger(__name__)

#: De qué método de `HeroicsLoader` sale cada tienda de Heroic. Steam va
#: aparte: tiene su propia caché en SQLite.
_HEROIC_GETTERS = {
    "gog": "get_gog_games",
    "epic": "get_epic_games",
    "amazon": "get_amazon_games",
}


def store_title(store: str, store_id: str, config=None) -> str | None:
    """
    El nombre que tiene `store_id` en `store`, o None si no se puede saber.

    Nunca lanza: se llama desde dentro de acciones que ya están a medias
    (desconocer un juego), y quedarse sin el nombre bonito no puede impedir
    que la acción termine. Quien llama decide con qué reemplazarlo.

    Sin caché a propósito: leer el índice de una tienda son milisegundos y
    esto se pide una vez por acción manual, mientras que un índice guardado
    en memoria envejecería a lo largo de la sesión —el carrusel puede estar
    horas abierto— y acabaría dando nombres de juegos que ya no tienes.
    """
    try:
        if config is None:
            from puntueitor.core.config import ConfigManager

            config = ConfigManager().get

        if store == "steam":
            return _steam_title(store_id, config)
        if store in _HEROIC_GETTERS:
            return _heroic_title(store, store_id, config)
    except Exception as error:  # noqa: BLE001 - es un nombre, no vale fallar
        logger.warning(f"no se pudo leer el título de {store}/{store_id}: {error}")
        return None

    logger.debug(f"no hay fuente de títulos para la tienda {store!r}")
    return None


def _steam_title(store_id: str, config) -> str | None:
    """De la caché de la biblioteca de Steam (`owned_games`)."""
    if not config.steam_user_id:
        return None

    from puntueitor.core.cachers.steam_user_cacher import SteamUserCacher

    games = SteamUserCacher(config.steam_user_id).get_all_games()
    if not games:
        return None

    # `appid` es entero en la caché y texto en `resolvers`/`unknown_games`.
    for game in games:
        if str(game.get("appid")) == str(store_id):
            return game.get("name") or None
    return None


def _heroic_title(store: str, store_id: str, config) -> str | None:
    """
    De los ficheros de biblioteca de Heroic (o Relic), en `store_cache`.

    La carpeta se busca igual que en el pipeline
    (`load_steam_library.load_library`): primero la que haya configurado el
    usuario y, si no, las de siempre.
    """
    from puntueitor.core.heroics import HeroicsLoader

    loader = HeroicsLoader()
    heroic_path = loader.find_heroic_path(config.heroic_path or None)
    if heroic_path is None:
        return None

    games = getattr(loader, _HEROIC_GETTERS[store])(heroic_path)
    for game in games or ():
        if str(game.get("app_name")) == str(store_id):
            return game.get("title") or None
    return None
