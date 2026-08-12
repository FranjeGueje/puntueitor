"""
Tipografía del frontend 3D: Hussar Print (Robert Jablonski / Cannot Into
Space Fonts), licencia SIL Open Font License 1.1 — ver
`assets/fonts/HussarPrint-OFL.txt`. Permite usar, modificar y redistribuir
el tipo de letra junto con el software sin más condición que no venderlo
por separado y no reutilizar su nombre reservado en derivados, así que
puede ir en el repo tal cual.

Un único punto de carga para que el título, la ficha, el banner de tiendas
y el submenú usen siempre la misma fuente — antes cada `OnscreenText` y
`DirectLabel` se quedaba con la fuente por defecto de Panda3D, que no pega
nada con el resto del estilo "caja de videojuego".
"""
from pathlib import Path

from panda3d.core import DynamicTextFont, FontPool

_FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "HussarPrintA.otf"

_cached_font: DynamicTextFont | None = None


def ui_font() -> DynamicTextFont | None:
    """
    La fuente de la interfaz, cargada una sola vez y reutilizada.

    Devuelve None si el fichero no está disponible (por ejemplo, si algún
    día se decide no distribuirlo) para que el llamante caiga con
    normalidad a la fuente por defecto de Panda3D en vez de reventar.
    """
    global _cached_font
    if _cached_font is None:
        _cached_font = FontPool.load_font(str(_FONT_PATH))
        if _cached_font is None:
            import logging
            logging.getLogger(__name__).warning(
                f"gui3d: no se pudo cargar la fuente en {_FONT_PATH}, "
                "usando la fuente por defecto de Panda3D"
            )
    return _cached_font
