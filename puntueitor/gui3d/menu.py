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
# Título en red velvet y separadores de sección en el azulito: colores
# intercambiados a propósito respecto a como estaban (el título era el
# azulito) para que el título destaque más fuerte que los rótulos de
# sección, que son un apoyo de lectura, no el foco de atención del menú.
TITLE_COLOR = (0.62, 0.09, 0.20, 1)

# Los elementos SIN foco van claramente apagados, no en blanco. El color del
# resaltado es el de la tienda del juego, y el de Epic es un gris casi negro
# que al aclararse para poder leerlo queda blanco roto: con los elementos
# normales en blanco, en los juegos de Epic el resaltado era invisible
# (comprobado renderizando el menú sobre uno). Apagando el resto, el
# elemento con foco destaca sea cual sea su tono.
ITEM_COLOR = (0.62, 0.63, 0.68, 1)

#: Para las líneas de un aviso que dicen qué se va a perder. Rojo claro y
#: no el granate del título (`TITLE_COLOR`): ese se eligió para un texto
#: grande, y a tamaño de rótulo sobre el panel oscuro apenas se lee.
WARNING_COLOR = (0.93, 0.42, 0.42, 1)
ITEM_COLOR_DISABLED = (0.35, 0.35, 0.40, 1)
HEADER_COLOR = (0.6, 0.8, 1, 1)
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

#: Cuántas filas se enseñan como mucho. Pasado ese número el menú se
#: desplaza en vez de crecer: la lista de géneros trae 23 entradas y un
#: panel con todas se salía por arriba y por abajo de la pantalla, con el
#: título fuera de cuadro y "Restaurar" cortado.
#:
#: 16 y no menos porque los menús largos "de verdad" —filtrar y ordenar, y
#: la configuración— tienen 15 filas cada uno y caben enteros; con el tope
#: en 10 se ponían a desplazarse sin necesidad. Y no más porque a partir de
#: 18 el panel ocupa la pantalla de arriba abajo (medido: 18 filas son 1,77
#: de los 2,0 que hay).
MAX_VISIBLE_ITEMS = 16

#: Indicadores de que hay más lista por encima o por debajo.
SCROLL_UP_MARK = "↑"
SCROLL_DOWN_MARK = "↓"
SCROLL_MARK_SCALE = 0.030
SCROLL_MARK_COLOR = (0.55, 0.57, 0.65, 1)

# Márgenes internos del panel.
TOP_PADDING = 0.075
TITLE_GAP = 0.085
BOTTOM_PADDING = 0.055

# Aire a los lados del texto más ancho. Era 0.07 y se quedaba corto en el
# menú de configuración: el Client ID de IGDB es una fila muy larga y el
# panel le quedaba pegado. No hace falta tocar `PANEL_MAX_HALF_WIDTH` — con
# 0.07 el tope ni siquiera llegaba a entrar en juego (medido: pedía 0.765 de
# los 0.95 permitidos), el panel simplemente iba justo de margen.
SIDE_PADDING = 0.12

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

    #: Valor actual, si el elemento enseña uno ("Terminados <N/A>"). Se pinta
    #: entre ángulos detrás de la etiqueta. None = el elemento no lleva valor.
    value: str | None = None

    #: Datos libres para quien construye el menú (por ejemplo, qué campo del
    #: juego toca una casilla). El menú no los mira.
    payload: dict = field(default_factory=dict)

    #: Color propio, para un rótulo que quiera destacar sobre el resto
    #: (p.ej. las secciones del menú de configuración). None = el color por
    #: defecto de su tipo (HEADER_COLOR o ITEM_COLOR).
    color: tuple[float, float, float, float] | None = None

    @property
    def focusable(self) -> bool:
        return self.kind != "header" and self.enabled

    def display_label(self) -> str:
        if self.kind == "check":
            return (CHECK_ON if self.checked else CHECK_OFF) + self.label
        if self.value is not None:
            return f"{self.label}  <{self.value}>"
        return self.label


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

        # Avisan de que la lista sigue por arriba o por abajo (ver `_window`).
        self._scroll_up = OnscreenText(
            parent=self.root, text=SCROLL_UP_MARK, scale=SCROLL_MARK_SCALE,
            fg=SCROLL_MARK_COLOR, align=TextNode.A_center, font=ui_font(),
        )
        self._scroll_down = OnscreenText(
            parent=self.root, text=SCROLL_DOWN_MARK, scale=SCROLL_MARK_SCALE,
            fg=SCROLL_MARK_COLOR, align=TextNode.A_center, font=ui_font(),
        )
        self._scroll_up.hide()
        self._scroll_down.hide()

        #: Primera fila de la ventana visible; sirve para saber si al mover
        #: el foco hay que rehacer el menú o basta con recolorear.
        self._window_start = 0

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

    def set_center_z(self, z: float) -> None:
        """
        Sube o baja el menú entero.

        Todo se coloca respecto al origen del nodo raíz, así que mover la
        raíz basta. Lo usa el menú de scoring, que comparte pantalla con la
        franja de descripción de abajo y centrado se solapaba con ella.
        """
        self.root.set_z(z)

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

    def _layout_scroll_marks(self, half: float, start: int, end: int) -> None:
        """Coloca (o esconde) las flechas de "hay más lista"."""
        if not self._scrolls:
            self._scroll_up.hide()
            self._scroll_down.hide()
            return

        # Justo bajo el título y justo sobre la pista, en el hueco que dejan
        # los márgenes; no ocupan fila propia para no comerse una entrada.
        self._scroll_up.set_pos(0, 0, half - TOP_PADDING - TITLE_GAP * 0.55)
        self._scroll_down.set_pos(0, 0, -half + BOTTOM_PADDING + HINT_GAP * 0.55)
        (self._scroll_up.show if start > 0 else self._scroll_up.hide)()
        (self._scroll_down.show if end < len(self._items) else self._scroll_down.hide)()

    @property
    def _scrolls(self) -> bool:
        return len(self._items) > MAX_VISIBLE_ITEMS

    def _window(self) -> tuple[int, int]:
        """
        Qué tramo de la lista se ve: `(primero, ultimo_excluido)`.

        La ventana sigue al foco pero se queda pegada a los extremos, para
        que al llegar al final de la lista no queden huecos en blanco
        debajo. Sin desplazamiento se devuelve la lista entera.
        """
        total = len(self._items)
        if not self._scrolls:
            return 0, total
        half = MAX_VISIBLE_ITEMS // 2
        start = max(0, min(self._focus_index - half, total - MAX_VISIBLE_ITEMS))
        return start, start + MAX_VISIBLE_ITEMS

    def _relayout(self) -> None:
        """Rehace la disposición conservando los elementos (para desplazar)."""
        for text in self._item_texts:
            text.destroy()
        self._item_texts.clear()
        self._rebuild()

    def _rebuild(self) -> None:
        """Recoloca panel, título, filas y pista según el contenido actual."""
        if self._panel is not None:
            self._panel.remove_node()

        has_hint = bool(self._hint_text.getText())
        start, end = self._window()
        self._window_start = start

        if self._scrolls:
            # Alto FIJO mientras se desplaza: si se midieran solo las filas
            # visibles, el panel encogería y crecería al pasar por los
            # rótulos de sección (que son más bajos) y daría un salto en
            # cada pulsación.
            content = MAX_VISIBLE_ITEMS * ITEM_HEIGHT
        else:
            content = self._content_height()

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
        # Se crean los textos de TODAS las filas, no solo las visibles: el
        # ancho del panel se mide de ellos y tiene que salir el mismo se mire
        # el tramo que se mire, o el menú cambiaría de ancho al desplazarse.
        # Las de fuera de la ventana se esconden justo después.
        for index, item in enumerate(self._items):
            height = HEADER_HEIGHT if item.kind == "header" else ITEM_HEIGHT
            visible = start <= index < end
            # El texto se ancla en su línea base, así que se baja algo más de
            # media fila para que quede centrado en el hueco que ocupa.
            text = self._make_item_text(item, z - height * _ITEM_BASELINE_FRACTION)
            self._item_texts.append(text)
            if visible:
                z -= height
            else:
                text.hide()

        if has_hint:
            self._hint_text.set_pos(0, 0, -half + BOTTOM_PADDING)
            self._hint_text.show()
        else:
            self._hint_text.hide()

        self._layout_scroll_marks(half, start, end)

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
            fg=item.color or (HEADER_COLOR if is_header else ITEM_COLOR),
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
        """Abre el menú DE NUEVO: se ve, y el foco vuelve al primer elemento."""
        self._visible = True
        self._focus_index = self._first_focusable()
        self._refresh_focus()
        self.root.show()

    def close(self) -> None:
        self._visible = False
        self.root.hide()

    def hide(self) -> None:
        """
        Aparta el menú para dejar paso a otra cosa, SIN tocar el foco.

        Distinto de `close()` solo en la intención, y distinto de `open()` en
        lo que importa: `open()` devuelve el foco al primer elemento, así que
        usarlo para volver de un submenú (o de un cuadro de texto) te dejaba
        en la primera fila en vez de en la que estabas editando.
        """
        self._visible = False
        self.root.hide()

    def show(self) -> None:
        """Lo vuelve a enseñar tal y como estaba, con su foco."""
        self._visible = True
        self.root.show()

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
                # Si el foco se ha salido del tramo visible hay que rehacer
                # el menú para desplazarlo; si no, basta con recolorear, que
                # es mucho más barato y es el caso normal.
                if self._window()[0] != self._window_start:
                    self._relayout()
                else:
                    self._refresh_focus()
                return

    def refresh_values(self) -> None:
        """
        Repinta las etiquetas tras cambiar los `value` de los elementos.

        Solo el texto: no se rehace el panel ni se recoloca nada, así que el
        foco se queda donde estaba. Es lo que se quiere al cambiar un valor
        con izquierda/derecha — rehacer el menú entero devolvería el foco al
        primer elemento en cada pulsación.

        El panel NO se reajusta al nuevo ancho a propósito: un valor más
        largo que el anterior ensancharía el menú a mitad de uso y daría un
        salto muy feo. Se dimensiona una vez, con `set_items`.
        """
        for item, text in zip(self._items, self._item_texts):
            text.setText(item.display_label())

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
