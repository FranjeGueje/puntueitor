"""
Prototipo visual aislado del carrusel 3D de Puntueitor.

No toca `core/` ni `gui/` (TUI) — usa datos de ejemplo en vez de
`LibraryService` para poder iterar rápido sobre el look, la cámara, el
movimiento del carrusel y los controles de teclado/mando antes de conectarlo
a la biblioteca real.

Ejecutar con:
    python -m puntueitor.gui3d.prototype
"""
import logging

from direct.gui.DirectGui import DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight,
    AntialiasAttrib,
    DirectionalLight,
    TextNode,
    WindowProperties,
    load_prc_file_data,
)

# Antialiasing (MSAA) de todo lo 3D — bordes rectos y curvas (las esquinas
# redondeadas del estuche) se ven escalonados sin esto. Tiene que fijarse
# ANTES de que ShowBase cree la ventana; hacerlo después no tiene efecto.
# Comprobado en runtime que el driver lo concede: `win.get_fb_properties()
# .get_multisamples()` devuelve 8 (el driver sube la petición de 4).
#
# `textures-power-2 none` desactiva el reescalado automático de Panda3D a
# potencias de dos. Por defecto (`down`) una carátula de 264x374 se
# reescalaba a 256x256 nada más cargarla: además de perder resolución,
# aplastaba una imagen 3:4 a un cuadrado y luego se reestiraba al mostrarla.
# El daño se notaba sobre todo en el fondo, que amplía esa misma textura a
# pantalla completa. Cualquier GPU con OpenGL moderno soporta texturas de
# tamaño arbitrario, así que el reescalado solo restaba calidad.
load_prc_file_data("", """
framebuffer-multisample 1
multisamples 4
textures-power-2 none
""")

from puntueitor.gui3d.background import Background
from puntueitor.gui3d.carousel import Carousel, CarouselEntry
from puntueitor.gui3d.covers import CoverLoader
from puntueitor.gui3d.gamepad_input import GamepadInput
from puntueitor.gui3d.real_data import build_real_entries
from puntueitor.gui3d.sample_data import build_sample_entries
from puntueitor.gui3d.submenu import Submenu

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WINDOW_TITLE = "Puntueitor 3D — prototipo de carrusel"
TITLE_TEXT_SCALE = 0.09
TITLE_TEXT_Y = 0.90
DESCRIPTION_TEXT_SCALE = 0.045
DESCRIPTION_WRAP = 60

# Barra inferior translúcida (estilo EmulationStation/Steam Big Picture):
# parte la pantalla en dos, con la descripción dentro sobre fondo negro
# semitransparente.
DESCRIPTION_BAR_COLOR = (0, 0, 0, 0.75)
DESCRIPTION_BAR_TOP_Z = -0.58

SUBMENU_OPTIONS = ["Ordenar", "Filtrar", "Configurar", "Enriquecedores", "Salir"]

# Cuánto se sube el carrusel entero para que quede pegado al título.
CAROUSEL_RAISE = 1.3

BACKGROUND_COLOR = (0.04, 0.04, 0.06, 1)

HELP_TEXT = (
    "<-  /  ->  o mando: navegar   -   Enter/A: seleccionar   -   "
    "Esc/Start: menu   -   Q: salir"
)


class Prototype(ShowBase):
    def __init__(self):
        super().__init__()

        # En modo offscreen (usado por los tests) self.win es un
        # GraphicsBuffer sin propiedades de ventana que fijar.
        if hasattr(self.win, "request_properties"):
            props = WindowProperties()
            props.set_title(WINDOW_TITLE)
            self.win.request_properties(props)

        self.disable_mouse()
        self.set_background_color(*BACKGROUND_COLOR)

        # Pedir un framebuffer multimuestreado por prc NO basta por sí solo:
        # Panda3D deja el multisampling desactivado en el pipe gráfico hasta
        # que algún nodo lo pide con `AntialiasAttrib`. Sin esta línea el
        # framebuffer tenía sus 8 muestras (`win.get_fb_properties()
        # .get_multisamples()` lo confirmaba) pero no se usaban: medido
        # renderizando una caja blanca sobre fondo negro y barriendo su
        # borde, la transición era 0.00 -> 1.00 de golpe, sin un solo píxel
        # intermedio, e idéntica con `multisamples 0` y con `multisamples 4`.
        # Con el atributo puesto, ese mismo borde pasa a tener cientos de
        # píxeles intermedios. Ojo: el valor informado por get_multisamples()
        # no sirve para comprobar esto — sale 8 aunque el AA esté apagado.
        self.render.set_antialias(AntialiasAttrib.M_multisample)

        self._setup_lighting()
        self._setup_camera()
        self._sync_lens_aspect_ratio()
        self.accept("window-event", self._on_window_event)
        self.background = Background(self)

        raw_entries, pending_downloads = build_real_entries() or build_sample_entries()
        entries = [
            CarouselEntry(
                key=e["key"], title=e["title"],
                description=e["description"], texture=e["texture"],
                stores=e.get("stores", frozenset()),
            )
            for e in raw_entries
        ]
        self.carousel_root = self.render.attach_new_node("carousel-root")
        self.carousel_root.set_z(CAROUSEL_RAISE)
        self.carousel = Carousel(self.carousel_root, entries)

        # Carátulas que aún no están en disco: se descargan en segundo plano
        # y se sustituyen en caliente cuando llegan (ver _update).
        self.cover_loader = CoverLoader()
        for key, igdb_id, cover_url in pending_downloads:
            self.cover_loader.request(key, igdb_id, cover_url)

        self._setup_hud()
        self._refresh_selection_text()

        self.submenu = Submenu(self.aspect2d, SUBMENU_OPTIONS)

        self._setup_keyboard()
        self.gamepad = GamepadInput(
            self,
            on_left=self._on_left,
            on_right=self._on_right,
            on_confirm=self._on_confirm,
            on_back=self._on_back,
            on_menu=self._on_toggle_menu,
        )

        self.task_mgr.add(self._update, "carousel-update")

    # ──────────────────────────────
    # Escena
    # ──────────────────────────────

    def _setup_lighting(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.set_color((0.45, 0.45, 0.5, 1))
        self.render.set_light(self.render.attach_new_node(ambient))

        sun = DirectionalLight("sun")
        sun.set_color((0.9, 0.9, 0.85, 1))
        sun_np = self.render.attach_new_node(sun)
        sun_np.set_hpr(20, -60, 0)
        self.render.set_light(sun_np)

    def _setup_camera(self) -> None:
        # Alejada respecto al primer prototipo (-8.5) para que el carrusel
        # ocupe menos pantalla mantieniendo las proporciones entre la caja
        # seleccionada y las vecinas (ver CAROUSEL_RAISE para la compensación
        # vertical, así queda a la misma distancia del título que antes).
        self.camera.set_pos(0, -15.3, 0.7)
        self.camera.look_at(0, -3, 0.15)

    def _setup_hud(self) -> None:
        self.title_text = OnscreenText(
            text="", pos=(0, TITLE_TEXT_Y), scale=TITLE_TEXT_SCALE,
            fg=(1, 1, 1, 1), align=TextNode.A_center, mayChange=True,
        )

        # Barra inferior a todo lo ancho, independiente del aspect ratio de
        # la ventana: aspect2d reescala X según get_aspect_ratio(), así que
        # el frame debe ir de -aspect a +aspect para tocar los dos bordes.
        # Ojo: aspect_ratio se lee de nuevo en cada resize (_on_window_event)
        # — cachearlo solo aquí lo dejaba desactualizado tras maximizar.
        self.description_frame = DirectFrame(
            parent=self.aspect2d,
            frameColor=DESCRIPTION_BAR_COLOR,
            frameSize=(-1, 1, -1.0, DESCRIPTION_BAR_TOP_Z),
            pos=(0, 0, 0),
        )

        self.description_text = OnscreenText(
            parent=self.description_frame, text="",
            pos=(0, DESCRIPTION_BAR_TOP_Z - 0.16), scale=DESCRIPTION_TEXT_SCALE,
            fg=(0.9, 0.9, 0.9, 1), align=TextNode.A_center,
            wordwrap=DESCRIPTION_WRAP, mayChange=True,
        )
        self.help_text = OnscreenText(
            parent=self.description_frame, text=HELP_TEXT,
            pos=(0, -0.93), scale=0.035,
            fg=(0.55, 0.55, 0.6, 1), align=TextNode.A_center, mayChange=False,
        )

        self._resize_description_frame()

    def _on_window_event(self, window) -> None:
        self._sync_lens_aspect_ratio()
        self._resize_description_frame()

    def _sync_lens_aspect_ratio(self) -> None:
        """
        Fuerza al lente de la cámara 3D Y a `aspect2d` (título, barra de
        descripción, submenú — todo el 2D) a coincidir con el aspect ratio
        real de la ventana.

        Bug real, reproducido en local: al pedir una ventana de 1920x1080,
        el gestor de ventanas la recorta a 1920x1008 (deja hueco para su
        barra de tareas), pero el aspect ratio se queda con el valor
        ORIGINALMENTE PEDIDO (1.778) en vez del real (1.905) — el ajuste
        automático de Panda3D (`ShowBase.windowEvent`) no lo corrige por sí
        solo en este caso.

        Usar `self.adjustWindowAspectRatio(...)` en vez de tocar
        `camLens.set_aspect_ratio()` directamente: la primera versión de
        este arreglo solo corregía el lente 3D (por eso las cajas se veían
        bien) pero dejaba la propia escala interna de `aspect2d` sin
        actualizar, así que el título y la barra de descripción — que
        cuelgan de `aspect2d`, no de la cámara 3D — seguían mal. Este método
        de ShowBase corrige ambos a la vez en una sola llamada.
        """
        self.adjustWindowAspectRatio(self.get_aspect_ratio())

    def _resize_description_frame(self) -> None:
        aspect = self.get_aspect_ratio()
        self.description_frame["frameSize"] = (-aspect, aspect, -1.0, DESCRIPTION_BAR_TOP_Z)

    # ──────────────────────────────
    # Entrada
    # ──────────────────────────────

    def _setup_keyboard(self) -> None:
        self.accept("arrow_left", self._on_left)
        self.accept("arrow_right", self._on_right)
        self.accept("enter", self._on_confirm)
        self.accept("escape", self._on_back)
        self.accept("q", self.userExit)

    def _on_left(self) -> None:
        if self.submenu.is_open:
            self.submenu.move_focus(-1)
        else:
            self.carousel.move(-1)
            self._refresh_selection_text()

    def _on_right(self) -> None:
        if self.submenu.is_open:
            self.submenu.move_focus(1)
        else:
            self.carousel.move(1)
            self._refresh_selection_text()

    def _on_confirm(self) -> None:
        if self.submenu.is_open:
            logger.info(f"gui3d: opción de submenú elegida: {self.submenu.focused_option!r}")
            self.submenu.close()
        else:
            logger.info(f"gui3d: seleccionado {self.carousel.selected.title!r}")

    def _on_back(self) -> None:
        if self.submenu.is_open:
            self.submenu.close()

    def _on_toggle_menu(self) -> None:
        if self.submenu.is_open:
            self.submenu.close()
        else:
            self.submenu.open()

    # ──────────────────────────────
    # Frame
    # ──────────────────────────────

    def _refresh_selection_text(self) -> None:
        entry = self.carousel.selected
        self.title_text.setText(entry.title)
        self.description_text.setText(entry.description)
        self.background.set_cover(self.carousel.selected_texture)

    def _update(self, task):
        self._check_lens_aspect_ratio()

        dt = globalClock.get_dt()
        self.carousel.update(dt)
        for key, texture in self.cover_loader.poll():
            self.carousel.set_texture(key, texture)
            if key == self.carousel.selected.key:
                self.background.set_cover(texture)
        return task.cont

    def _check_lens_aspect_ratio(self) -> None:
        """
        Red de seguridad además de `_on_window_event`: si el gestor de
        ventanas recorta la ventana pedida (visto en local: pides 1920x1080
        y te da 1920x1008 para dejar hueco a su barra de tareas) antes de
        que Panda3D termine de arrancar, no se dispara ningún "window-event"
        que lo corrija — el lente nace ya con el aspect ratio equivocado y
        se queda así, sin ningún cambio posterior que lo dispare. Comprobar
        la diferencia una vez por frame es barato y se autocorrige sin
        depender de cazar ese evento.
        """
        current = self.get_aspect_ratio()
        if abs(current - self.camLens.get_aspect_ratio()) > 1e-4:
            self._sync_lens_aspect_ratio()
            self._resize_description_frame()

    def destroy(self):
        self.cover_loader.shutdown()
        super().destroy()


def main() -> None:
    app = Prototype()
    app.run()


if __name__ == "__main__":
    main()
