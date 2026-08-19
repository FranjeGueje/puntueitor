"""
De dónde salen los juegos de cada tienda.

Un proveedor por tienda, todos con la misma interfaz (`LibraryProvider`):
piden la biblioteca a la web, la guardan y saben servirla de la copia
guardada cuando no hay conexión. El pipeline recorre proveedores y ya no
sabe si detrás hay HTTP, un fichero o una caché.
"""
from puntueitor.core.providers.amazon import AmazonProvider
from puntueitor.core.providers.base import LibraryProvider
from puntueitor.core.providers.epic import EpicProvider
from puntueitor.core.providers.gog import GOGProvider
from puntueitor.core.providers.steam import SteamProvider


def build_providers(config) -> dict:
    """
    Un proveedor por cada tienda ACTIVA en la configuración.

    Se construyen aquí y no en el pipeline para que añadir una tienda sea
    tocar este paquete y nada más. Construir un proveedor no habla con la
    red ni abre sesión: eso pasa en `fetch()`, y solo si hace falta.
    """
    from puntueitor.core.models import Stores

    providers = {}

    if config.steam_is_active:
        providers[Stores.STEAM] = SteamProvider(
            api_key=config.steam_api_key, user_id=config.steam_user_id,
        )

    tiendas = {
        Stores.GOG: (config.gog_is_active, GOGProvider),
        Stores.EPIC: (config.epic_is_active, EpicProvider),
        Stores.AMAZON: (config.amazon_is_active, AmazonProvider),
    }
    for store, (activa, clase) in tiendas.items():
        if activa:
            providers[store] = clase()

    return providers


__all__ = [
    "LibraryProvider", "SteamProvider", "GOGProvider", "EpicProvider",
    "AmazonProvider", "build_providers",
]
