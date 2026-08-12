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

from panda3d.core import (
    DynamicTextFont,
    Filename,
    FontPool,
    TextProperties,
    TextPropertiesManager,
)

_FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "HussarPrintA.otf"

# Grosor del contorno con el que se simula la negrita (ver `ui_font_bold`),
# en unidades de la propia fuente. Hussar Print viene en un solo grosor y
# Panda3D no tiene negrita sintética, así que se engorda el glifo con un
# contorno de su mismo color. `feather=0` para que el borde salga duro; con
# feather el contorno se difumina y el número se ve borroso en vez de más
# gordo.
_BOLD_OUTLINE_WIDTH = 0.8
_BOLD_OUTLINE_FEATHER = 0.0

#: Nombre registrado en `TextPropertiesManager` para el superíndice (usado
#: por la marca "[1]" de la puntuación SteamDB en `ficha.py`). Vive aquí,
#: junto a la carga de la fuente, porque es la misma clase de configuración
#: global de texto y así solo hay un sitio que la registra.
SUPERSCRIPT_PROPERTY = "sup"

_cached_font: DynamicTextFont | None = None
_cached_bold_font: DynamicTextFont | None = None


def ui_font() -> DynamicTextFont | None:
    """
    La fuente de la interfaz, cargada una sola vez y reutilizada.

    Devuelve None si el fichero no está disponible (por ejemplo, si algún
    día se decide no distribuirlo) para que el llamante caiga con
    normalidad a la fuente por defecto de Panda3D en vez de reventar.

    De paso registra `SUPERSCRIPT_PROPERTY`: un texto puesto entre
    `\x01sup\x01` y `\x02` sale más pequeño y desplazado hacia arriba, el
    mismo efecto que un "º". La sintaxis de estructura de `TextNode` no es
    obvia y está verificada empíricamente, no sacada de memoria — `\x01`
    ABRE Y CIERRA el nombre de la propiedad en el MISMO carácter (no hace
    falta un segundo `\x01` de cierre de nombre), y un `\x02` suelto hace de
    pop. Otras combinaciones razonables (`\x01nombre\x02...\x02`, que es la
    que uno esperaría por analogía con abrir/cerrar) no funcionan y Panda3D
    ni siquiera avisa con claridad — devuelve el texto sin la propiedad
    aplicada, con un aviso de "Unclosed push_properties" o "Unknown
    TextProperties" según cuál se pruebe.
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

        superscript = TextProperties()
        superscript.set_text_scale(0.55)
        superscript.set_glyph_shift(0.55)
        TextPropertiesManager.get_global_ptr().set_properties(
            SUPERSCRIPT_PROPERTY, superscript,
        )

    return _cached_font


def ui_font_bold(color: tuple[float, float, float, float]) -> DynamicTextFont | None:
    """
    Variante "negrita" de la fuente, para los números de las etiquetas.

    Hussar Print se distribuye en un solo grosor y Panda3D no genera
    negrita sintética, así que se engorda el glifo dándole un contorno de
    su MISMO color: el resultado es un trazo más grueso, no un borde
    visible. De ahí que haga falta el color como argumento — un contorno
    de otro color se vería como un perfilado, no como negrita.

    Es una instancia de fuente SEPARADA, cargada con `DynamicTextFont`
    directamente en vez de con `FontPool.load_font`: el pool cachea por
    ruta y devuelve el mismo objeto para el mismo fichero (comprobado), así
    que ponerle el contorno a la fuente del pool se lo pondría también al
    título, la ficha y el banner, que comparten esa instancia. El contorno
    es una propiedad de la FUENTE, no del `TextNode`, y por eso no se puede
    aplicar solo a un texto concreto sin duplicar la fuente.
    """
    global _cached_bold_font
    if _cached_bold_font is None:
        font = DynamicTextFont(Filename.from_os_specific(str(_FONT_PATH)))
        if not font.is_valid():
            import logging
            logging.getLogger(__name__).warning(
                f"gui3d: no se pudo cargar la fuente negrita en {_FONT_PATH}"
            )
            return None
        font.set_outline(color, _BOLD_OUTLINE_WIDTH, _BOLD_OUTLINE_FEATHER)
        _cached_bold_font = font

    return _cached_bold_font
