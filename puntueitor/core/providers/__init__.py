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

    Sale del registro de tiendas (`core/stores/`), así que añadir una no se
    toca aquí. Construir un proveedor no habla con la red ni abre sesión: eso
    pasa en `fetch()`, y solo si hace falta.
    """
    from puntueitor.core import stores

    return {
        spec.store: spec.provider(config)
        for spec in stores.active(config)
    }


__all__ = [
    "LibraryProvider", "SteamProvider", "GOGProvider", "EpicProvider",
    "AmazonProvider", "build_providers",
]
