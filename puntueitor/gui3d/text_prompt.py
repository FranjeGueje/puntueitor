"""
Cuadro de texto en primer plano, para los filtros que piden escribir algo
(el nombre y la duración máxima).

Se abre por encima del menú, con su propio panel redondeado, y solo puede
haber uno a la vez. Acepta con Enter y cancela con Esc o B, que es lo mismo
que hace el resto de la interfaz.

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
PANEL_HALF_WIDTH = 0.75
PANEL_HALF_HEIGHT = 0.24

TITLE_COLOR = (0.6, 0.8, 1, 1)
TITLE_SCALE = 0.058
TITLE_Z = 0.11

HINT_COLOR = (0.55, 0.57, 0.65, 1)
HINT_SCALE = 0.032
HINT_Z = -0.17

ENTRY_SCALE = 0.062
ENTRY_Z = -0.035
#: Ancho del cuadro en caracteres. Con la escala de arriba, 22 llenan el
#: panel sin salirse; el texto más largo sigue cabiendo porque `DirectEntry`
#: hace scroll horizontal solo.
ENTRY_WIDTH = 22

ENTRY_TEXT_COLOR = (0.95, 0.95, 0.98, 1)
ENTRY_BACK_COLOR = (0.16, 0.17, 0.22, 1)


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
            width=ENTRY_WIDTH,
            numLines=1,
            focus=0,
            frameColor=ENTRY_BACK_COLOR,
            text_fg=ENTRY_TEXT_COLOR,
            text_font=font,
            # El cuadro se dibuja hacia la derecha desde su origen, así que
            # se desplaza media anchura para que quede centrado en el panel.
            pos=(-ENTRY_WIDTH * ENTRY_SCALE / 2.0, 0, ENTRY_Z),
            command=self._on_enter,
        )

        self._on_accept: Callable[[str], None] | None = None
        self._on_cancel: Callable[[], None] | None = None
        self._visible = False

    @property
    def is_open(self) -> bool:
        return self._visible

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
