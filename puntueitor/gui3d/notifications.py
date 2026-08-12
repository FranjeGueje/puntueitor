"""
Avisos efímeros arriba a la derecha ("Mostrando ocultos", "Ocultando juegos"...).

Un solo aviso a la vez, a la altura del título del juego y pegado al borde
derecho. Aparece fundiendo, se queda un rato y se va fundiendo. Nada de cola
de mensajes: son avisos de "acabas de hacer esto", y si llegan dos seguidos
lo que interesa es el último, no leer el primero con retraso.

Va aparte de `app.py` porque no depende de nada suyo — se le da un nodo padre
y ya — y porque así la animación (que es lo único con truco aquí) queda en un
sitio acotado en vez de repartida entre los métodos de la aplicación.
"""
from direct.gui.OnscreenText import OnscreenText
from direct.interval.IntervalGlobal import Func, LerpColorScaleInterval, Sequence, Wait
from panda3d.core import NodePath, TextNode, TransparencyAttrib

from puntueitor.gui3d.fonts import ui_font

#: Tiempos del aviso, tal y como se pidieron: entra en un segundo, se queda
#: dos, y se va en otro.
FADE_IN_DURATION = 1.0
HOLD_DURATION = 2.0
FADE_OUT_DURATION = 1.0

TEXT_SCALE = 0.055
TEXT_COLOR = (0.85, 0.90, 1.0, 1)

#: Separación respecto al borde derecho de la pantalla.
SIDE_MARGIN = 0.06

#: Altura: la misma que el título del juego (`app.TITLE_TEXT_Y`). No se
#: importa de `app` para no crear una dependencia circular — `app` ya importa
#: este módulo —, así que si allí se mueve el título hay que moverlo aquí.
TEXT_Z = 0.90


class Notifier:
    """Muestra avisos de usar y tirar. Reutiliza un único `OnscreenText`."""

    def __init__(self, parent: NodePath, aspect_ratio: float = 1.0):
        self._text = OnscreenText(
            parent=parent,
            text="",
            scale=TEXT_SCALE,
            fg=TEXT_COLOR,
            align=TextNode.A_right,
            font=ui_font(),
            mayChange=True,
        )
        # Sin esto el fundido no se ve: `set_color_scale` con alfa solo tiene
        # efecto si el nodo tiene mezcla por transparencia activada.
        self._text.set_transparency(TransparencyAttrib.M_alpha)
        self._text.hide()

        self._sequence: Sequence | None = None
        self.resize(aspect_ratio)

    def resize(self, aspect_ratio: float) -> None:
        """
        Recoloca el aviso al ancho actual de la ventana.

        `aspect2d` va de -aspect a +aspect en X, así que pegarlo a la derecha
        depende del aspect ratio y hay que rehacerlo en cada cambio de tamaño
        (mismo motivo que `app._resize_ficha`).
        """
        self._text.set_pos(aspect_ratio - SIDE_MARGIN, 0, TEXT_Z)

    def show(self, message: str) -> None:
        """
        Enseña un aviso, sustituyendo al que hubiera.

        Si ya había uno en marcha se corta con `finish()`, que además de
        pararlo lo deja en su estado final (invisible): sin eso, el fundido
        de entrada del nuevo aviso arrancaría desde la opacidad a la que se
        hubiera quedado el anterior y el `startColorScale` de abajo se
        pelearía con la interpolación todavía viva sobre el mismo nodo.
        """
        if self._sequence is not None:
            self._sequence.finish()

        self._text.setText(message)
        self._sequence = Sequence(
            Func(self._text.show),
            LerpColorScaleInterval(
                self._text, FADE_IN_DURATION, (1, 1, 1, 1),
                startColorScale=(1, 1, 1, 0),
            ),
            Wait(HOLD_DURATION),
            LerpColorScaleInterval(self._text, FADE_OUT_DURATION, (1, 1, 1, 0)),
            Func(self._text.hide),
        )
        self._sequence.start()

    def destroy(self) -> None:
        if self._sequence is not None:
            self._sequence.finish()
            self._sequence = None
        self._text.destroy()
