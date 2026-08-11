"""
Paleta de colores por tienda, compartida entre el color del estuche
(`game_case.py`), el banner de tiendas (`case_banner.py`) y la carátula de
relleno mientras se descarga la real (`real_data.py`) — un solo sitio para
mantener la paleta consistente en todo el prototipo, en vez de la misma
tabla de colores copiada en varios módulos.

No hay logos reales de Steam/Epic/GOG/Amazon en el repo (temas de marca para
material no oficial de esas tiendas); el color identifica la tienda en su
lugar.
"""
from collections.abc import Iterable

from puntueitor.core.models import Stores

# Orden de preferencia cuando un juego está en varias tiendas a la vez.
STORE_PRIORITY = (Stores.STEAM, Stores.GOG, Stores.EPIC, Stores.AMAZON)

STORE_COLORS: dict[Stores, tuple[float, float, float]] = {
    Stores.STEAM: (0.16, 0.22, 0.34),
    Stores.GOG: (0.48, 0.24, 0.58),
    Stores.EPIC: (0.22, 0.22, 0.24),
    Stores.AMAZON: (0.82, 0.53, 0.13),
}

# Para juegos sin ninguna tienda reconocida ("Otros").
DEFAULT_COLOR: tuple[float, float, float] = (0.08, 0.08, 0.09)


def primary_store_color(stores: Iterable[Stores]) -> tuple[float, float, float]:
    """
    Color de la tienda preferente entre `stores`, siguiendo
    `STORE_PRIORITY` (Steam > GOG > Epic > Amazon), o `DEFAULT_COLOR` si
    `stores` está vacío o no contiene ninguna tienda reconocida.
    """
    present = set(stores)
    for store in STORE_PRIORITY:
        if store in present:
            return STORE_COLORS[store]
    return DEFAULT_COLOR
