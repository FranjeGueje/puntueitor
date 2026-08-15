"""
Cuadro de texto en primer plano, para los filtros que piden escribir algo
(el nombre y la duración máxima).

Se abre por encima del menú, con su propio panel redondeado, y solo puede
haber uno a la vez. Acepta con Enter y cancela con Esc o B, que es lo mismo
que hace el resto de la interfaz.

Aquí NUNCA se deja de poder escribir. Cuando el texto deja de caber, la letra
encoge (ver `fit_scale` y `_apply_scale`); y cuando ya no puede encoger más,
el texto se desliza siguiendo al cursor (ver `overflow`). Al borrar, la letra
vuelve a crecer sola hasta su tamaño normal en cuanto cabe.

No es un adorno: el cuadro lo comparten los filtros con los campos de
Configuración, y ahí se escriben cosas como el Client Secret de IGDB o la
carpeta de Heroic, que no entran ni de lejos a tamaño normal.

OJO con una cosa que no es evidente y que hay que respetar desde fuera: un
`DirectEntry` con el foco NO se queda con las pulsaciones de teclado. Panda3D
las sigue repartiendo por el messenger, así que los atajos de la aplicación
("o" para los ocultos, "x" para los filtros...) se disparan igual mientras
escribes. Por eso `app.App` suelta sus atajos al abrir esto y los vuelve a
coger al cerrarlo (`_release_shortcuts` / `_bind_shortcuts`); este módulo no
puede arreglarlo por su cuenta.
"""
from collections.abc import Callable

from direct.gui.DirectGui import DirectEntry
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import NodePath, TextNode

from puntueitor.gui3d.fonts import ui_font
from puntueitor.gui3d.rounded_panel import make_rounded_panel

PANEL_COLOR = (0.06, 0.06, 0.09, 0.98)
PANEL_RADIUS = 0.055
PANEL_HALF_WIDTH = 1.05
PANEL_HALF_HEIGHT = 0.24

TITLE_COLOR = (0.6, 0.8, 1, 1)
TITLE_SCALE = 0.058
TITLE_Z = 0.11

HINT_COLOR = (0.55, 0.57, 0.65, 1)
HINT_SCALE = 0.032
HINT_Z = -0.17

ENTRY_Z = -0.035

#: Lo que mide el cuadro EN PANTALLA (unidades de aspect2d). Es lo único que
#: no se mueve nunca: cuando la letra encoge, lo que cambia es cuánto cabe
#: dentro, no el marco.
ENTRY_UNITS = 1.9
#: Tamaño de letra normal.
ENTRY_SCALE = 0.062
#: Hasta dónde encoge la letra. NO es un tope de lo que se puede escribir:
#: pasado este punto se sigue tecleando igual y lo que hace el cuadro es
#: deslizar el texto para no perder de vista el cursor (ver `overflow`, más
#: abajo). Es solo el tamaño por debajo del cual ya no se leería.
ENTRY_MIN_SCALE = 0.030

ENTRY_TEXT_COLOR = (0.95, 0.95, 0.98, 1)
ENTRY_BACK_COLOR = (0.16, 0.17, 0.22, 1)


def fit_scale(text_width: float) -> float:
    """
    A qué escala cabe en el cuadro un texto de ancho `text_width`.

    El ancho va en unidades de texto (lo que devuelve `TextNode.calcWidth`),
    no en caracteres: la fuente es proporcional y una "i" no ocupa lo que una
    "W".

    Nunca crece por encima de `ENTRY_SCALE` —un texto corto se ve del tamaño
    de siempre— ni baja de `ENTRY_MIN_SCALE`, que es donde ya costaría leerlo.
    """
    if text_width <= 0:
        return ENTRY_SCALE
    return max(ENTRY_MIN_SCALE, min(ENTRY_SCALE, ENTRY_UNITS / text_width))


class TextPrompt:
    """Cuadro de texto modal. Se construye una vez y se reutiliza."""

    def __init__(self, parent: NodePath):
        self.root = parent.attach_new_node("text-prompt")
        self.root.hide()

        make_rounded_panel(
            self.root,
            -PANEL_HALF_WIDTH, PANEL_HALF_WIDTH,
            -PANEL_HALF_HEIGHT, PANEL_HALF_HEIGHT,
            PANEL_RADIUS, PANEL_COLOR,
        )

        font = ui_font()
        self._title = OnscreenText(
            parent=self.root, text="", scale=TITLE_SCALE, fg=TITLE_COLOR,
            align=TextNode.A_center, font=font, pos=(0, TITLE_Z), mayChange=True,
        )
        self._hint = OnscreenText(
            parent=self.root, text="", scale=HINT_SCALE, fg=HINT_COLOR,
            align=TextNode.A_center, font=font, pos=(0, HINT_Z), mayChange=True,
        )

        # `initialText`/`focus` se ponen en cada `open()`, no aquí: el cuadro
        # se reutiliza para el nombre y para la duración.
        self._entry = DirectEntry(
            parent=self.root,
            text="",
            scale=ENTRY_SCALE,
            width=ENTRY_UNITS / ENTRY_SCALE,
            numLines=1,
            # Esto es lo que quita el tope de tecleo. Sin `overflow`, el ancho
            # del cuadro es un límite duro: `PGEntry` deja de aceptar teclas
            # cuando el texto formateado llega a él, y encoger la letra solo
            # corría el límite más lejos. Con `overflow` (y una sola línea,
            # que es lo único con lo que funciona) `PGEntry` desactiva ese
            # corte, desplaza el texto para que el cursor siga a la vista y
            # recorta el dibujo al ancho del cuadro, así que lo que se sale no
            # invade el panel.
            overflow=1,
            focus=0,
            frameColor=ENTRY_BACK_COLOR,
            text_fg=ENTRY_TEXT_COLOR,
            text_font=font,
            command=self._on_enter,
        )

        # El margen y el alto del marco los eligió el propio PGEntry al
        # montarse; se copian tal cual para poder rehacer el marco al cambiar
        # de escala sin inventarse un aspecto distinto del que ya tenía.
        izquierda, derecha, abajo, arriba = self._entry.guiItem.getFrame()
        self._pad = -izquierda
        self._frame_bottom = abajo
        self._frame_top = arriba

        # Con lo que mide el texto se recalcula todo esto en cada tecla.
        self._scale = 0.0
        self._apply_scale(ENTRY_SCALE)

        # `DirectEntry` es un `DirectObject`, así que puede escuchar los
        # eventos que su propio PGEntry lanza al teclear y al borrar. Los dos
        # hacen falta: solo con el de teclear la letra encogería y no volvería
        # a crecer nunca al vaciar el cuadro.
        self._entry.accept(self._entry.guiItem.getTypeEvent(), self._fit)
        self._entry.accept(self._entry.guiItem.getEraseEvent(), self._fit)

        self._on_accept: Callable[[str], None] | None = None
        self._on_cancel: Callable[[], None] | None = None
        self._visible = False

    @property
    def is_open(self) -> bool:
        return self._visible

    def _apply_scale(self, scale: float) -> None:
        """
        Pone el cuadro a esa escala SIN cambiar lo que mide en pantalla.

        El truco está en subir `width` en la misma proporción en que baja la
        escala: así el marco mide lo mismo en pantalla pero entra más texto.
        `width` es lo que `PGEntry` toma como ancho útil del cuadro, o sea
        cuánto se ve antes de empezar a desplazar el texto y por dónde recorta
        el dibujo, así que mantenerlo cuadrado con la escala es lo que hace que
        el desplazamiento empiece justo en el borde.

        El marco se fija a mano con `frameSize` porque `DirectEntry.setup()`
        no lo rehace: cambia el tope, pero deja el marco como estaba.
        """
        if scale == self._scale:
            return
        self._scale = scale

        # Se despeja de (ancho + 2·pad) · escala == ENTRY_UNITS, para que el
        # marco quede clavado y no dé un saltito al cambiar de tamaño.
        ancho = ENTRY_UNITS / scale - 2 * self._pad
        self._entry["width"] = ancho
        self._entry["frameSize"] = (
            -self._pad, ancho + self._pad, self._frame_bottom, self._frame_top,
        )
        self._entry.setScale(scale)
        # El cuadro se dibuja hacia la derecha desde su origen, así que se
        # desplaza media anchura para quedar centrado en el panel.
        self._entry.setPos(-ENTRY_UNITS / 2.0 + self._pad * scale, 0, ENTRY_Z)

    def _fit(self, *_args) -> None:
        """
        Ajusta el tamaño de la letra a lo que hay escrito.

        Se llama en cada tecla, y casi siempre no hace nada: mientras el texto
        quepa, la escala sale la misma y `_apply_scale` se vuelve por donde
        vino.

        El ancho se MIDE con el TextNode que el propio `DirectEntry` ya tiene
        montado (escala 1, así que devuelve unidades de texto directamente).
        Contar caracteres no valdría: la fuente es proporcional.
        """
        ancho = self._entry.onscreenText.textNode.calcWidth(self._entry.get())
        self._apply_scale(fit_scale(ancho))

    def open(
        self,
        title: str,
        hint: str,
        initial: str,
        on_accept: Callable[[str], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self._title.setText(title)
        self._hint.setText(hint)
        self._on_accept = on_accept
        self._on_cancel = on_cancel

        self._entry.enterText(initial)
        # El cursor al final del texto que ya había, no al principio: si se
        # vuelve a abrir un filtro para retocarlo, lo natural es seguir
        # escribiendo donde estaba.
        self._entry.setCursorPosition(len(initial))
        # Lo que ya estaba guardado puede ser largo de por sí (un secret de
        # IGDB, la ruta de Heroic), así que el ajuste se hace ya al abrir y no
        # solo al teclear.
        self._fit()
        self._entry["focus"] = 1

        self._visible = True
        self.root.show()

    def close(self) -> None:
        # Quitarle el foco es importante: un `DirectEntry` enfocado sigue
        # tragándose las teclas aunque su nodo esté oculto.
        self._entry["focus"] = 0
        self._visible = False
        self.root.hide()

    def accept_text(self) -> None:
        """Confirma lo escrito (Enter, o el botón A)."""
        if self._visible:
            self._on_enter(self._entry.get())

    def cancel(self) -> None:
        """Cierra sin aplicar (Esc o B)."""
        if not self._visible:
            return
        cancel = self._on_cancel
        self.close()
        if cancel:
            cancel()

    def _on_enter(self, text: str) -> None:
        accept = self._on_accept
        self.close()
        if accept:
            accept(text.strip())
