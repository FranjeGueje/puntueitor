"""
Cómo se llama un juego EN SU TIENDA, no en IGDB.

Los dos nombres no son el mismo, y la diferencia importa al desconocer un
juego: se desconoce precisamente porque IGDB lo identificó mal, así que
apuntarlo en `unknown_games` con el nombre de IGDB borra la pista de qué juego
era de verdad. Con el de la tienda, la lista de desconocidos sigue diciendo lo
mismo que dice tu biblioteca en la tienda, que es donde vas a mirar
para identificarlo a mano.

Es también el criterio que ya usa el escaneo: un desconocido que nace ahí se
apunta con `BaseResolver._extract_title(raw)`, o sea el título de la tienda.
Esto es lo que hace que las dos vías llenen la tabla igual.

No hace falta red ni volver a escanear: la misma caché de la que come el
pipeline está en disco.
"""
import logging

logger = logging.getLogger(__name__)


def store_title(store: str, store_id: str, config=None) -> str | None:
    """
    El nombre que tiene `store_id` en `store`, o None si no se puede saber.

    Nunca lanza: se llama desde dentro de acciones que ya están a medias
    (desconocer un juego), y quedarse sin el nombre bonito no puede impedir
    que la acción termine. Quien llama decide con qué reemplazarlo.

    Sale de la caché de bibliotecas (`StoreLibraryCacher`), que es la copia
    de lo último que sirvió cada tienda. No se llama a la red: aquí solo hace
    falta un nombre, y pedir la biblioteca entera para uno sería absurdo —si
    el juego está en tu biblioteca, está en esa caché.
    """
    try:
        from puntueitor.core.cachers.store_library_cacher import StoreLibraryCacher

        return StoreLibraryCacher(store).title_of(store_id)
    except Exception as error:  # noqa: BLE001 - es un nombre, no vale fallar
        logger.warning(f"no se pudo leer el título de {store}/{store_id}: {error}")
        return None
