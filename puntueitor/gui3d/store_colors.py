"""
Paleta de colores por tienda, compartida entre el color del estuche
(`game_case.py`), el banner de tiendas (`case_banner.py`) y la carátula de
relleno mientras se descarga la real (`real_data.py`) — un solo sitio para
mantener la paleta consistente en todo el frontend 3D, en vez de la misma
tabla de colores copiada en varios módulos.

No hay logos reales de Steam/Epic/GOG/Amazon en el repo (temas de marca para
material no oficial de esas tiendas); el color identifica la tienda en su
lugar.
"""
from collections.abc import Iterable

from puntueitor.core import stores
from puntueitor.core.models import Stores

# Los dos salen del registro de tiendas (`core/stores/`): el color lo declara
# cada tienda en su módulo, y la prioridad es el orden del registro, que es
# también el orden en que se pintan en los menús. Así una tienda nueva trae su
# color puesto en vez de salir del color por defecto hasta que alguien se
# acuerde de esta tabla.
STORE_PRIORITY = tuple(spec.store for spec in stores.all_stores())

STORE_COLORS: dict[Stores, tuple[float, float, float]] = {
    spec.store: spec.color for spec in stores.all_stores()
}

# Para juegos sin ninguna tienda reconocida ("Otros").
DEFAULT_COLOR: tuple[float, float, float] = (0.08, 0.08, 0.09)

#: Hasta dónde sube el canal más alto en `as_text_color()`. No llega a 1.0
#: para que el color no se confunda con el blanco puro del texto normal.
_TEXT_COLOR_PEAK = 0.95


def as_text_color(
    color: tuple[float, float, float],
) -> tuple[float, float, float, float]:
    """
    La misma tienda, en un tono legible como TEXTO sobre fondo oscuro.

    Los colores de `STORE_COLORS` están pensados para pintar el estuche y el
    chip del banner, que son superficies con texto blanco encima, así que
    son oscuros a propósito (Steam es un azul marino de 0.16/0.22/0.34).
    Usados tal cual para el texto del elemento resaltado de un menú —panel
    casi negro— no se leerían: Epic quedaría gris carbón sobre gris carbón.

    Se sube el brillo hasta que el canal más alto llega casi al máximo, lo
    que conserva el tono (la proporción entre canales no cambia) y solo
    cambia la intensidad, así que la tienda se sigue reconociendo por el
    color. Los grises muy oscuros como Epic acaban en un blanco roto, que es
    lo correcto: es su identidad de marca.
    """
    peak = max(color)
    if peak <= 0.0:
        return (0.95, 0.95, 0.95, 1.0)
    scale = _TEXT_COLOR_PEAK / peak
    r, g, b = (min(1.0, channel * scale) for channel in color)
    return (r, g, b, 1.0)


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
