"""
Tipografías del frontend 3D.

Texto: Hussar Print (Robert Jablonski / Cannot Into Space Fonts), licencia
SIL Open Font License 1.1 — ver `assets/fonts/HussarPrint-OFL.txt`. Permite
usar, modificar y redistribuir el tipo de letra junto con el software sin
más condición que no venderlo por separado y no reutilizar su nombre
reservado en derivados, así que puede ir en el repo tal cual.

Iconos: PromptFont (Yukari "Shinmera" Hafner, https://shinmera.com/promptfont),
misma licencia SIL OFL — ver `assets/buttons/PromptFont-OFL.txt`. Es una
fuente normal (OTF), no un atlas de imágenes: cada tecla/botón es un glifo
en un punto de código Unicode del bloque "Control Pictures" y de rangos de
símbolos matemáticos reutilizados a propósito por la fuente para esto. Se
usa exactamente igual que Hussar Print — se carga con `DynamicTextFont` y
se manda como texto normal — así que no hace falta ningún sistema de
iconos aparte ni texturas por botón.

Un único punto de carga para que el título, la ficha, el banner de tiendas
y el submenú usen siempre la misma fuente — antes cada `OnscreenText` y
`DirectLabel` se quedaba con la fuente por defecto de Panda3D, que no pega
nada con el resto del estilo "caja de videojuego".
"""
from pathlib import Path

from panda3d.core import DynamicTextFont, FontPool, TextProperties, TextPropertiesManager

_FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "HussarPrintA.otf"
_ICON_FONT_PATH = Path(__file__).parent / "assets" / "buttons" / "PromptFont.otf"

#: Nombre registrado en `TextPropertiesManager` para el superíndice (usado
#: por la marca "[1]" de la puntuación SteamDB en `ficha.py`). Vive aquí,
#: junto a la carga de la fuente, porque es la misma clase de configuración
#: global de texto y así solo hay un sitio que la registra.
SUPERSCRIPT_PROPERTY = "sup"

#: Nombre registrado para conmutar a PromptFont dentro de un texto (ver
#: `icon_font()` y `icon_markup()`).
ICON_PROPERTY = "icon"

_cached_font: DynamicTextFont | None = None
_cached_icon_font: DynamicTextFont | None = None

# Un carácter por control, construido con `chr()` a partir del punto de
# código en vez de tecleado literal: son glifos del bloque "Control
# Pictures" y de símbolos matemáticos que PromptFont reutiliza como
# iconos, no atajos de teclado reales, y un carácter mal transcrito a mano
# no avisa — dibuja el glifo equivocado en silencio. Cada punto de código
# se verificó contra `glyphs.json` del paquete de PromptFont antes de
# usarlo (la lista de nombres no está documentada en el propio .otf).
ICON_KEYBOARD_LEFT = chr(0x23F4)              # keyboard-left
ICON_KEYBOARD_RIGHT = chr(0x23F5)             # keyboard-right
ICON_KEYBOARD_UP = chr(0x23F6)                # keyboard-up
ICON_KEYBOARD_DOWN = chr(0x23F7)              # keyboard-down
ICON_KEYBOARD_ENTER = chr(0x242E)             # keyboard-enter
ICON_KEYBOARD_SPACE = chr(0x243A)             # keyboard-space
ICON_KEYBOARD_ESCAPE = chr(0x242F)            # keyboard-escape
ICON_KEYBOARD_TAB = chr(0x242B)               # keyboard-tab
ICON_KEYBOARD_O = chr(0xFF2F)                 # keyboard-o
ICON_KEYBOARD_Q = chr(0xFF31)                 # keyboard-q
ICON_KEYBOARD_W = chr(0xFF37)                 # keyboard-w
ICON_KEYBOARD_X = chr(0xFF38)                 # keyboard-x
# Las cuatro caras van en el orden en que están en el mando, no alfabético:
# 0x21D0 izquierda (X), 0x21D1 arriba (Y), 0x21D2 derecha (B), 0x21D3 abajo
# (A) — mismo orden que las flechas dobles de Unicode que ocupan esos puntos.
ICON_XBOX_X = chr(0x21D0)                     # xbox-x
ICON_XBOX_Y = chr(0x21D1)                     # xbox-y
ICON_XBOX_B = chr(0x21D2)                     # xbox-b
ICON_XBOX_A = chr(0x21D3)                     # xbox-a
# El dpad tiene glifos "left"/"right"/"left-right", pero en un solo color
# (sin el resaltado de color del brazo activo que lleva la fuente original)
# los tres se ven exactamente igual que la cruz completa — probado
# renderizando los cuatro uno junto a otro. El icono de STICK con flechas a
# los lados sí distingue izquierda/derecha a simple vista, y además es más
# preciso: la navegación acepta cruceta Y stick indistintamente.
ICON_GAMEPAD_LEFT_RIGHT = chr(0x21D4)         # analog-left-right
ICON_GAMEPAD_UP_DOWN = chr(0x21D5)            # analog-up-down
ICON_GAMEPAD_START = chr(0x21F8)              # gamepad-start
ICON_GAMEPAD_L1 = chr(0x21B0)                 # gamepad-l1
ICON_GAMEPAD_R1 = chr(0x21B1)                 # gamepad-r1
ICON_GAMEPAD_L2 = chr(0x21B2)                 # gamepad-l2
# "Select" y "Back" son el mismo botón físico con dos nombres según la
# generación del mando; PromptFont solo trae el dibujo rotulado SELECT.
ICON_GAMEPAD_SELECT = chr(0x21F7)             # gamepad-select


def icon_markup(text: str) -> str:
    """
    Envuelve `text` en la marca de estructura que conmuta a PromptFont.

    Mismo mecanismo que `SUPERSCRIPT_PROPERTY`: `\x01icon\x01` empuja la
    propiedad, el `\x02` suelto la saca. Un helper porque escribir los
    caracteres de control a mano en cada sitio que mezcla iconos con texto
    normal es propenso a errores de tecleo silenciosos (un `\x02` de más o
    de menos no avisa, simplemente dibuja mal).
    """
    return f"\x01{ICON_PROPERTY}\x01{text}\x02"


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


def icon_font() -> DynamicTextFont | None:
    """
    Fuente de iconos de botones/teclas (PromptFont), cargada una sola vez.

    De paso registra `ICON_PROPERTY`: un texto envuelto con `icon_markup()`
    conmuta a esta fuente y vuelve a Hussar Print al cerrar la marca, así
    que un mismo `OnscreenText`/`TextNode` puede mezclar libremente
    palabras normales e iconos de botones sin necesitar varios nodos ni
    posicionarlos a mano — es el mismo truco de `\x01nombre\x01...\x02` que
    ya usa `SUPERSCRIPT_PROPERTY`, aplicado a conmutar de fuente en vez de
    a escalar.

    `set_text_scale`/`set_glyph_shift` compensan que PromptFont no comparte
    métricas con Hussar Print: sin ajustar, los iconos salían visiblemente
    más pequeños y más altos que el texto de alrededor — ajustado sobre el
    render, no hay forma de calcularlo de las métricas de las fuentes.
    """
    global _cached_icon_font
    if _cached_icon_font is None:
        _cached_icon_font = FontPool.load_font(str(_ICON_FONT_PATH))
        if _cached_icon_font is None:
            import logging
            logging.getLogger(__name__).warning(
                f"gui3d: no se pudo cargar la fuente de iconos en {_ICON_FONT_PATH}"
            )
            return None

        icon = TextProperties()
        icon.set_font(_cached_icon_font)
        icon.set_text_scale(1.55)
        icon.set_glyph_shift(-0.08)
        TextPropertiesManager.get_global_ptr().set_properties(
            ICON_PROPERTY, icon,
        )

    return _cached_icon_font
