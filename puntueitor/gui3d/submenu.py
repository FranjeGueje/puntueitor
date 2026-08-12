"""
Submenú de opciones superpuesto, navegable con teclado o mando — el
equivalente 3D al diálogo de configuración de la TUI (`gui/screens/*.py`).

Es deliberadamente un placeholder visual: las opciones no hacen nada todavía,
solo demuestran el patrón de apertura/cierre/navegación con foco resaltado
que se reutilizará para los submenús reales (ordenar, filtrar, configurar).
"""
from direct.gui.DirectGui import DGG, DirectFrame, DirectLabel
from panda3d.core import NodePath, TextNode

from puntueitor.gui3d.fonts import ui_font

_PANEL_COLOR = (0.05, 0.05, 0.08, 0.92)
_ITEM_COLOR = (1, 1, 1, 1)
_ITEM_COLOR_FOCUSED = (1, 0.85, 0.2, 1)


class Submenu:
    """Panel de opciones simple, con una opción resaltada a la vez."""

    def __init__(self, parent: NodePath, options: list[str]):
        self.options = options
        self._focus_index = 0
        self._visible = False

        self.frame = DirectFrame(
            parent=parent,
            frameColor=_PANEL_COLOR,
            frameSize=(-0.55, 0.55, -0.05 - 0.11 * len(options), 0.15),
            pos=(0, 0, 0),
        )
        self.frame.hide()

        font = ui_font()

        DirectLabel(
            parent=self.frame,
            text="Opciones",
            text_scale=0.06,
            text_fg=(0.6, 0.8, 1, 1),
            text_align=TextNode.A_center,
            text_font=font,
            pos=(0, 0, 0.06),
            frameColor=(0, 0, 0, 0),
        )

        self._labels = []
        for i, option in enumerate(options):
            label = DirectLabel(
                parent=self.frame,
                text=option,
                text_scale=0.05,
                text_align=TextNode.A_center,
                text_font=font,
                pos=(0, 0, -0.08 - 0.11 * i),
                frameColor=(0, 0, 0, 0),
            )
            self._labels.append(label)

        self._refresh_focus()

    @property
    def is_open(self) -> bool:
        return self._visible

    def open(self) -> None:
        self._visible = True
        self._focus_index = 0
        self._refresh_focus()
        self.frame.show()

    def close(self) -> None:
        self._visible = False
        self.frame.hide()

    def move_focus(self, direction: int) -> None:
        if not self.options:
            return
        self._focus_index = (self._focus_index + direction) % len(self.options)
        self._refresh_focus()

    @property
    def focused_option(self) -> str:
        return self.options[self._focus_index]

    def _refresh_focus(self) -> None:
        for i, label in enumerate(self._labels):
            focused = i == self._focus_index
            label["text_fg"] = _ITEM_COLOR_FOCUSED if focused else _ITEM_COLOR
            label["text_scale"] = 0.058 if focused else 0.05
