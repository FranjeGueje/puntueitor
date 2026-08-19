"""
El registro de tiendas: la única lista de qué tiendas hay.

Quien necesite recorrer las tiendas —los menús de las dos interfaces, el
pipeline, los colores del carrusel, el log— pregunta aquí en vez de llevar su
propia copia de la lista. Ese era el problema: el mismo hecho escrito en once
sitios y sincronizado a mano.

**El orden importa** y es el de abajo: es el orden en que se pintan en los
menús, y también el de prioridad de color cuando un juego está en varias
tiendas a la vez (ver `gui3d/store_colors.py`).

Para añadir una tienda, ver `spec.py`.
"""
from puntueitor.core.models import Stores
from puntueitor.core.stores import amazon, epic, gog, steam
from puntueitor.core.stores.spec import StoreSpec

#: Todas las tiendas, en orden de presentación.
REGISTRY: tuple[StoreSpec, ...] = (
    steam.SPEC,
    gog.SPEC,
    epic.SPEC,
    amazon.SPEC,
)

_POR_TIENDA = {spec.store: spec for spec in REGISTRY}


def all_stores() -> tuple[StoreSpec, ...]:
    """Todas, en orden."""
    return REGISTRY


def with_session() -> tuple[StoreSpec, ...]:
    """
    Las que tienen sesión que iniciar.

    Steam no está, y no por olvido: no ofrece OAuth a terceros. Lo declara su
    propio módulo con `session=None`, así que esto no hay que mantenerlo.
    """
    return tuple(spec for spec in REGISTRY if spec.has_session)


def resolvable_by_id() -> tuple[str, ...]:
    """
    Las claves de las tiendas cuyos juegos se pueden volver a identificar por
    su id de tienda. Lo declara cada una en su módulo.
    """
    return tuple(spec.key for spec in REGISTRY if spec.resolvable_by_id)


def get(store) -> StoreSpec:
    """La tienda `store`, aceptando el enum o su clave en texto."""
    return _POR_TIENDA[Stores(str(store))]


def find(store) -> StoreSpec | None:
    """Como `get`, pero None si no está registrada."""
    try:
        return get(store)
    except (KeyError, ValueError):
        return None


def active(config) -> tuple[StoreSpec, ...]:
    """Las marcadas en la configuración, en orden."""
    return tuple(
        spec for spec in REGISTRY
        if getattr(config, spec.config_flag, False)
    )


__all__ = [
    "StoreSpec", "REGISTRY",
    "all_stores", "with_session", "resolvable_by_id", "get", "find", "active",
]
