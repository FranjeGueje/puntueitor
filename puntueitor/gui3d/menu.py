"""
Menús superpuestos del frontend 3D: panel redondeado, título en negrita y
una lista VERTICAL de elementos con uno resaltado.

Sustituye al antiguo `submenu.py`, que era un único panel de opciones fijo,
navegable con izquierda/derecha (heredado de cuando lo único que había en
pantalla era el carrusel horizontal). Aquí un menú es un objeto reutilizable
y los menús se apilan: abrir uno encima de otro y volver con B/Esc es cosa
de `app.App`, que lleva la pila.

Los elementos son de tres tipos:

    action    lo normal: se elige con A/Enter y dispara algo
    check     lleva una casilla; A/Enter la marca o desmarca en el sitio
    header    rótulo de sección, NO se puede enfocar (se salta al navegar)

El resaltado usa el color de la tienda del juego seleccionado en el
carrusel — el mismo que el estuche y el banner de su carátula, aclarado para
que se lea (`store_colors.as_text_color`). Así el menú "pertenece"
visualmente al juego sobre el que se abrió en vez de tener un amarillo fijo
que no pega con nada de lo que hay detrás.
"""
from dataclasses import dataclass, field

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import NodePath, TextNode

from puntueitor.gui3d.fonts import ui_font
from puntueitor.gui3d.rounded_panel import make_rounded_panel

# Colores base. El del resaltado lo pone `set_accent_color()`; este es solo
# el que se usa hasta que llegue el primero (menús construidos antes de que
# haya un juego seleccionado).
PANEL_COLOR = (0.06, 0.06, 0.09, 0.96)
TITLE_COLOR = (0.6, 0.8, 1, 1)

# Los elementos SIN foco van claramente apagados, no en blanco. El color del
# resaltado es el de la tienda del juego, y el de Epic es un gris casi negro
# que al aclararse para poder leerlo queda blanco roto: con los elementos
# normales en blanco, en los juegos de Epic el resaltado era invisible
# (comprobado renderizando el menú sobre uno). Apagando el resto, el
# elemento con foco destaca sea cual sea su tono.
ITEM_COLOR = (0.62, 0.63, 0.68, 1)
ITEM_COLOR_DISABLED = (0.35, 0.35, 0.40, 1)
HEADER_COLOR = (0.55, 0.57, 0.65, 1)
HINT_COLOR = (0.55, 0.57, 0.65, 1)
DEFAULT_ACCENT = (1, 0.85, 0.2, 1)

PANEL_RADIUS = 0.055

# El ancho del panel se ajusta a su contenido entre estos dos límites (ver
# `_half_width`). Fijo no vale: la pista del menú de scoring lleva una tecla
# más ("configurar") y se salía por los lados del panel, mientras que el de
# confirmar salida tiene dos opciones cortas y le sobraba la mitad.
PANEL_MIN_HALF_WIDTH = 0.42
PANEL_MAX_HALF_WIDTH = 0.95

TITLE_SCALE = 0.062
ITEM_SCALE = 0.050
HEADER_SCALE = 0.038
HINT_SCALE = 0.032

# Alto de cada fila y de cada rótulo de sección. Los headers ocupan menos
# porque son texto más pequeño y no llevan casilla.
ITEM_HEIGHT = 0.082
HEADER_HEIGHT = 0.062

#: A qué altura de su hueco va la línea base de una fila. Algo más de la
#: mitad porque el texto crece hacia ARRIBA desde su línea base.
_ITEM_BASELINE_FRACTION = 0.62

# Márgenes internos del panel.
TOP_PADDING = 0.075
TITLE_GAP = 0.085
BOTTOM_PADDING = 0.055
SIDE_PADDING = 0.07

# Hueco entre la última fila y la pista del pie. Tiene que ser MAYOR que el
# resto de márgenes porque el texto de una fila se dibuja a media altura de
# su hueco (`_ITEM_BASELINE_FRACTION`), así que bajo la última línea base
# solo queda una fracción de fila; con un hueco pequeño, la pista se subía
# encima del último elemento en vez de quedar debajo.
HINT_GAP = 0.075

#: Cuánto crece el elemento enfocado. Sutil a propósito: el color ya lo
#: distingue, y un salto grande hace "bailar" la lista al navegar porque las
#: filas de al lado parecen moverse.
FOCUS_SCALE_BOOST = 1.12

#: Casillas de los elementos "check". De texto, no un asset: entran en el
#: mismo `OnscreenText` que la etiqueta y así no hay que alinear un icono
#: aparte con la línea base del texto.
#:
#: Las dos marcas tienen que ocupar EXACTAMENTE lo mismo. Marcar una casilla
#: solo debería encender la equis, pero si la marca cambia de ancho, la
#: etiqueta se desplaza de golpe al pulsar — y al hacerlo varias veces
#: seguidas la fila da un salto lateral muy feo. Por eso las filas con
#: casilla van además alineadas a la izquierda y no centradas: centradas, el
#: salto se repartiría a los dos lados aunque las marcas midieran igual.
CHECK_ON = "[X]  "
CHECK_OFF = "[ ]  "

#: Cuánto se sangra una fila con casilla respecto al borde del panel, para
#: que no quede pegada al canto redondeado.
_CHECK_ITEM_INDENT = SIDE_PADDING * 1.6


@dataclass
class MenuItem:
    """Un elemento de menú. `key` es lo que recibe el callback al elegirlo."""

    key: str
    label: str
    kind: str = "action"
    checked: bool = False
    enabled: bool = True

    #: Datos libres para quien construye el menú (por ejemplo, qué campo del
    #: juego toca una casilla). El menú no los mira.
    payload: dict = field(default_factory=dict)

    @property
    def focusable(self) -> bool:
        return self.kind != "header" and self.enabled

    def display_label(self) -> str:
        if self.kind != "check":
            return self.label
        return (CHECK_ON if self.checked else CHECK_OFF) + self.label


class Menu:
    """
    Un menú superpuesto. Se construye una vez y se abre/cierra cuantas veces
    haga falta; `set_items()` permite rehacer su contenido (lo necesita el
    menú de juego, cuyas casillas dependen del juego seleccionado).
    """

    def __init__(
        self,
        parent: NodePath,
        title: str,
        items: list[MenuItem] | None = None,
        hint: str = "",
    ):
        self.title = title
        self._items: list[MenuItem] = []
        self._focus_index = 0
        self._accent = DEFAULT_ACCENT
        self._visible = False

        self.root = parent.attach_new_node("menu")
        self.root.hide()

        self._panel: NodePath | None = None
        self._item_texts: list[OnscreenText] = []

        self._title_text = OnscreenText(
            parent=self.root,
            text=title,
            scale=TITLE_SCALE,
            fg=TITLE_COLOR,
            align=TextNode.A_center,
            font=ui_font(),
            mayChange=True,
        )
        self._hint_text = OnscreenText(
            parent=self.root,
            text=hint,
            scale=HINT_SCALE,
            fg=HINT_COLOR,
            align=TextNode.A_center,
            font=ui_font(),
            mayChange=True,
        )

        self.set_items(items or [])

    # ──────────────────────────────
    # Contenido
    # ──────────────────────────────

    def set_items(self, items: list[MenuItem]) -> None:
        """
        Reemplaza los elementos y rehace el panel a su nuevo tamaño.

        El foco se lleva al primer elemento enfocable, no se conserva: los
        menús que se rehacen lo hacen porque han cambiado de juego, y
        mantener el índice dejaría el foco en una fila que ya no significa
        lo mismo.
        """
        for text in self._item_texts:
            text.destroy()
        self._item_texts.clear()

        self._items = items
        self._focus_index = self._first_focusable()

        self._rebuild()

    def set_title(self, title: str) -> None:
        self.title = title
        self._title_text.setText(title)

    def _first_focusable(self) -> int:
        for i, item in enumerate(self._items):
            if item.focusable:
                return i
        return 0

    def _content_height(self) -> float:
        return sum(
            HEADER_HEIGHT if item.kind == "header" else ITEM_HEIGHT
            for item in self._items
        )

    @staticmethod
    def _text_width(text: OnscreenText) -> float:
        """
        Ancho real de un texto ya compuesto, en las unidades de la pantalla.

        `TextNode.get_width()` lo da en unidades de la fuente, así que hay
        que multiplicarlo por la escala a la que se dibuja. Se le pregunta al
        TextNode DESPUÉS de asignarle el texto — es quien sabe lo que ocupa,
        contando el ancho de cada glifo y los iconos intercalados, que es
        justo lo que no se puede estimar contando caracteres.
        """
        return text.textNode.get_width() * text["scale"][0]

    def _half_width(self) -> float:
        """Medio ancho del panel: lo que pida el texto más ancho, acotado."""
        widest = max(
            [self._text_width(self._title_text), self._text_width(self._hint_text)]
            + [self._text_width(text) for text in self._item_texts],
            default=0.0,
        )
        # Las filas con casilla no van centradas sino sangradas desde el
        # borde, así que ocupan su ancho MÁS la sangría, no la mitad a cada
        # lado; se comparan en las mismas unidades pasándolo a medio ancho.
        half = widest / 2.0 + SIDE_PADDING
        if any(item.kind == "check" for item in self._items):
            checks = max(
                (
                    self._text_width(text)
                    for text, item in zip(self._item_texts, self._items)
                    if item.kind == "check"
                ),
                default=0.0,
            )
            half = max(half, (checks + _CHECK_ITEM_INDENT + SIDE_PADDING) / 2.0)
        return min(PANEL_MAX_HALF_WIDTH, max(PANEL_MIN_HALF_WIDTH, half))

    def _rebuild(self) -> None:
        """Recoloca panel, título, filas y pista según el contenido actual."""
        if self._panel is not None:
            self._panel.remove_node()

        content = self._content_height()
        has_hint = bool(self._hint_text.getText())

        # El panel se construye centrado en vertical: se calcula el alto
        # total y se reparte a partes iguales arriba y abajo del origen, así
        # el menú queda siempre centrado en pantalla independientemente de
        # cuántos elementos tenga.
        total = TOP_PADDING + TITLE_GAP + content + BOTTOM_PADDING
        if has_hint:
            total += HINT_GAP
        half = total / 2.0

        # Tres coordenadas, no dos: `OnscreenText` hereda de `NodePath` y su
        # `set_pos` es el de NodePath — el `pos=(x, z)` de dos elementos solo
        # vale en el constructor (mismo detalle que en `app._layout_ficha_rows`).
        z = half - TOP_PADDING
        self._title_text.set_pos(0, 0, z)

        z -= TITLE_GAP
        for item in self._items:
            height = HEADER_HEIGHT if item.kind == "header" else ITEM_HEIGHT
            # El texto se ancla en su línea base, así que se baja algo más de
            # media fila para que quede centrado en el hueco que ocupa.
            self._item_texts.append(
                self._make_item_text(item, z - height * _ITEM_BASELINE_FRACTION)
            )
            z -= height

        if has_hint:
            self._hint_text.set_pos(0, 0, z - HINT_GAP)
            self._hint_text.show()
        else:
            self._hint_text.hide()

        # El panel se crea DESPUÉS que los textos porque su ancho sale de
        # medirlos, y solo se pueden medir una vez compuestos.
        half_width = self._half_width()
        self._panel = make_rounded_panel(
            self.root,
            -half_width, half_width, -half, half,
            PANEL_RADIUS, PANEL_COLOR,
        )
        # Detrás del texto: dentro de un mismo nodo Panda3D dibuja por orden
        # de creación, y aquí el panel es el último en crearse justamente
        # para poder medir, así que sin esto taparía todo lo demás.
        self._panel.set_bin("background", 0)

        # Las filas con casilla se alinean al borde ya conocido del panel.
        for text, item in zip(self._item_texts, self._items):
            if item.kind == "check":
                text.set_x(-half_width + _CHECK_ITEM_INDENT)

        self._refresh_focus()

    def _make_item_text(self, item: MenuItem, z: float) -> OnscreenText:
        is_header = item.kind == "header"
        is_check = item.kind == "check"
        return OnscreenText(
            parent=self.root,
            text=item.display_label(),
            scale=HEADER_SCALE if is_header else ITEM_SCALE,
            fg=HEADER_COLOR if is_header else ITEM_COLOR,
            align=TextNode.A_left if is_check else TextNode.A_center,
            font=ui_font(),
            # La x de las casillas depende del ancho final del panel, que
            # todavía no se conoce; la fija `_rebuild` al terminar.
            pos=(0, z),
            mayChange=True,
        )

    # ──────────────────────────────
    # Estado
    # ──────────────────────────────

    @property
    def is_open(self) -> bool:
        return self._visible

    @property
    def items(self) -> list[MenuItem]:
        return self._items

    @property
    def focused_item(self) -> MenuItem | None:
        if not self._items:
            return None
        return self._items[self._focus_index]

    def set_accent_color(self, color: tuple[float, float, float, float]) -> None:
        """Color del elemento resaltado (el de la tienda del juego actual)."""
        if color == self._accent:
            return
        self._accent = color
        self._refresh_focus()

    def open(self) -> None:
        self._visible = True
        self._focus_index = self._first_focusable()
        self._refresh_focus()
        self.root.show()

    def close(self) -> None:
        self._visible = False
        self.root.hide()

    # ──────────────────────────────
    # Navegación
    # ──────────────────────────────

    def move_focus(self, direction: int) -> None:
        """
        Mueve el foco arriba (-1) o abajo (+1), saltando los rótulos de
        sección y los elementos deshabilitados, y dando la vuelta al llegar
        al final.

        El recorrido está acotado a una vuelta completa: si NINGÚN elemento
        es enfocable (un menú que solo tiene rótulos), sin ese tope esto
        daría vueltas para siempre.
        """
        if not self._items or direction == 0:
            return

        index = self._focus_index
        for _ in range(len(self._items)):
            index = (index + direction) % len(self._items)
            if self._items[index].focusable:
                self._focus_index = index
                self._refresh_focus()
                return

    def toggle_focused(self) -> bool:
        """
        Marca/desmarca el elemento enfocado si es una casilla.

        Devuelve si de verdad ha cambiado algo, para que el llamante sepa si
        tiene que persistirlo.
        """
        item = self.focused_item
        if item is None or item.kind != "check":
            return False

        item.checked = not item.checked
        self._item_texts[self._focus_index].setText(item.display_label())
        return True

    def _refresh_focus(self) -> None:
        for i, (item, text) in enumerate(zip(self._items, self._item_texts)):
            if item.kind == "header":
                continue
            focused = i == self._focus_index
            if focused:
                text["fg"] = self._accent
                text["scale"] = ITEM_SCALE * FOCUS_SCALE_BOOST
            else:
                text["fg"] = ITEM_COLOR if item.enabled else ITEM_COLOR_DISABLED
                text["scale"] = ITEM_SCALE
