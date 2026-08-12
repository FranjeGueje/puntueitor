"""
Frontend 3D de Puntueitor: carrusel de cajas de juego con ficha, navegable
con teclado o mando.

Alternativa a la TUI (`gui/`), no un reemplazo: las dos leen la misma
biblioteca cacheada y ninguna toca `core/`. Es solo lectura — no lanza el
pipeline ni pide nada a IGDB; lo único que baja de la red son las carátulas
que falten, y en segundo plano.

Ejecutar con:
    python -m puntueitor.gui3d.app
    python -m puntueitor.gui3d.app --resolution 1920x1080
    python -m puntueitor.gui3d.app --fhd
"""
import argparse
import logging
import re
import sys

from direct.gui.DirectGui import DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.interval.IntervalGlobal import LerpColorScaleInterval, LerpPosInterval, Parallel
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

# Resoluciones con nombre para --hd/--fhd/--wxga/--wuxga. WXGA y WUXGA no
# tienen una única definición estándar; se usan aquí los tamaños de panel
# más comunes (1280x800 y 1920x1200, ambos 16:10).
RESOLUTION_PRESETS = {
    "hd": (1280, 720),
    "fhd": (1920, 1080),
    "wxga": (1280, 800),
    "wuxga": (1920, 1200),
}

_RESOLUTION_RE = re.compile(r"^(\d+)x(\d+)$", re.IGNORECASE)


def _parse_resolution_arg(value: str) -> tuple[int, int]:
    match = _RESOLUTION_RE.match(value.strip())
    if not match:
        raise argparse.ArgumentTypeError(
            f"resolución inválida: {value!r} (formato esperado: ANCHOxALTO, p.ej. 1920x1080)"
        )
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError(f"resolución inválida: {value!r} (ancho y alto deben ser positivos)")
    return width, height


def parse_args(argv: list[str] | None = None) -> tuple[int, int] | None:
    """Resuelve la resolución de ventana pedida por línea de comandos, si hay alguna."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--resolution", type=_parse_resolution_arg, metavar="ANCHOxALTO",
        help="Resolución de ventana, p.ej. 1920x1080",
    )
    for name, (width, height) in RESOLUTION_PRESETS.items():
        group.add_argument(
            f"--{name}", dest="preset", action="store_const", const=name,
            help=f"Resolución de ventana {width}x{height}",
        )
    args = parser.parse_args(argv)
    if args.resolution is not None:
        return args.resolution
    if args.preset is not None:
        return RESOLUTION_PRESETS[args.preset]
    return None

from puntueitor.gui3d.background import Background
from puntueitor.gui3d.carousel import Carousel, CarouselEntry
from puntueitor.gui3d.covers import CoverLoader, load_cover_texture
from puntueitor.gui3d.ficha import FIELD_LABELS, build_description, build_values
from puntueitor.gui3d.fonts import (
    ICON_GAMEPAD_L2,
    ICON_GAMEPAD_LEFT_RIGHT,
    ICON_GAMEPAD_SELECT,
    ICON_GAMEPAD_START,
    ICON_GAMEPAD_UP_DOWN,
    ICON_KEYBOARD_DOWN,
    ICON_KEYBOARD_ENTER,
    ICON_KEYBOARD_ESCAPE,
    ICON_KEYBOARD_LEFT,
    ICON_KEYBOARD_O,
    ICON_KEYBOARD_RIGHT,
    ICON_KEYBOARD_SPACE,
    ICON_KEYBOARD_TAB,
    ICON_KEYBOARD_UP,
    ICON_KEYBOARD_X,
    ICON_XBOX_A,
    ICON_XBOX_B,
    ICON_XBOX_X,
    ICON_XBOX_Y,
    icon_font,
    icon_markup,
    ui_font,
)
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.gui3d import menus
from puntueitor.gui3d.gamepad_input import GamepadInput
from puntueitor.gui3d.menu import Menu
from puntueitor.gui3d.notifications import Notifier
from puntueitor.gui3d.real_data import build_real_entries
from puntueitor.gui3d.sample_data import build_sample_entries
from puntueitor.gui3d.store_colors import as_text_color, primary_store_color

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WINDOW_TITLE = "Puntueitor 3D"
TITLE_TEXT_SCALE = 0.09
TITLE_TEXT_Y = 0.90

# Ficha inferior translúcida (estilo EmulationStation/Steam Big Picture):
# parte la pantalla en dos, con los datos del juego dentro sobre fondo negro
# semitransparente.
#
# Dos columnas, no una lista larga: en vertical solo caben unas ocho líneas
# antes de comerse el carrusel, y la ficha tiene ocho campos MÁS la sinopsis.
# Con los campos a la izquierda y la sinopsis a la derecha, cada mitad usa el
# alto entero de la ficha y no hay que recortar nada.
FICHA_BAR_COLOR = (0, 0, 0, 0.75)
# De -0.36 a -0.16: la ficha pasa de un 32% a un 42% de la pantalla. El
# límite no es arbitrario — por encima de -0.16 empieza a comerse la caja
# seleccionada del carrusel, no solo su reflejo (comprobado renderizando).
FICHA_BAR_TOP_Z = -0.16

# La ficha se aparta al abrir un menú, para que no compita con él, y vuelve
# al cerrar el último. Deslizarla hacia abajo Y desvanecerla a la vez en
# vez de solo lo uno o lo otro: solo desvanecer deja el bulto del panel
# oscuro asomando por debajo del menú (que no ocupa toda la pantalla);
# solo deslizar dejaría un salto brusco de opacidad al final del recorrido.
# Combinado con `Parallel`, sigue siendo una única animación barata: dos
# lerps sobre un nodo cada vez, nada de geometría ni texturas de por medio.
FICHA_ANIM_DURATION = 0.22
FICHA_ANIM_SLIDE = 0.12

FICHA_LABEL_SCALE = 0.034
FICHA_LINE_HEIGHT = 0.048
FICHA_TOP_MARGIN = 0.075
FICHA_SIDE_MARGIN = 0.07
FICHA_LABEL_COLOR = (0.62, 0.64, 0.72, 1)
FICHA_VALUE_COLOR = (0.93, 0.93, 0.95, 1)

# Las etiquetas se alinean a la DERECHA y los valores a la izquierda a partir
# de esta separación, así las dos columnas quedan a plomo sin depender de lo
# larga que sea cada etiqueta.
FICHA_LABEL_COLUMN = 0.38
FICHA_VALUE_GAP = 0.02

# Reparto horizontal: qué fracción del ancho útil se lleva la columna de
# campos. El resto es para la sinopsis. Los valores se parten en varias
# líneas dentro de su columna en vez de seguir de largo — un juego con
# muchos géneros se metía por encima del texto de la sinopsis.
FICHA_FIELDS_COLUMN_FRACTION = 0.55
DESCRIPTION_COLUMN_GAP = 0.05
DESCRIPTION_TEXT_SCALE = 0.040

# Cuántas posiciones a cada lado de la selección se van pidiendo carátulas.
# Más ancho que el radio visible del carrusel para que la carátula llegue
# antes de que el usuario se plante en esa caja.
COVER_PRELOAD_RADIUS = 10

# Además de las de alrededor, el resto de la biblioteca se va descargando
# poco a poco mientras haya hueco. Se encolan de pocas en pocas, no todas de
# golpe, para que las de alrededor de la selección (que son las que se están
# viendo) no queden esperando detrás de cientos de peticiones de relleno.
COVER_BACKFILL_INFLIGHT = 6

# Navegación mantenida. Al dejar pulsada una dirección, el carrusel se
# desplaza solo: primero espera NAV_REPEAT_DELAY para no disparar de más en
# una pulsación corta, y luego repite cada vez más rápido, de
# NAV_REPEAT_INTERVAL a NAV_REPEAT_MIN_INTERVAL, para poder recorrer una
# biblioteca de más de mil juegos sin machacar el botón.
NAV_REPEAT_DELAY = 0.35
NAV_REPEAT_INTERVAL = 0.12
NAV_REPEAT_MIN_INTERVAL = 0.045
NAV_REPEAT_ACCEL_TIME = 1.2

# Tope de repeticiones por frame, por si el frame se alarga (un tirón, o la
# ventana recuperando el foco): sin él, un dt grande se traduciría en un
# salto de decenas de posiciones de una sentada.
NAV_MAX_STEPS_PER_FRAME = 4

# El fondo se cambia solo cuando la navegación se para un momento. Regenerar
# el desenfoque cuesta unos 9 ms (medido sobre carátulas reales), que a la
# velocidad de repetición mínima serían casi 200 ms de CPU por segundo y un
# tirón en cada frame. El título y la ficha sí se actualizan al instante,
# porque son solo texto.
BACKGROUND_SETTLE_DELAY = 0.18

# Los menús se navegan con el mismo mecanismo de repetición mantenida que el
# carrusel, pero más despacio: una lista tiene entre dos y trece elementos,
# no mil, y a la cadencia del carrusel se pasa de largo constantemente.
MENU_REPEAT_DELAY = 0.40
MENU_REPEAT_INTERVAL = 0.16

# Cuánto se sube el carrusel entero para que quede pegado al título.
CAROUSEL_RAISE = 1.3

BACKGROUND_COLOR = (0.04, 0.04, 0.06, 1)

def _build_help_text() -> str:
    """
    Construye la barra de ayuda con iconos de tecla/botón en vez de sus
    nombres en texto ("Enter/A" -> el dibujo de la tecla Enter y el botón
    A). Función, no constante: `icon_markup()` necesita que `icon_font()`
    ya haya registrado `ICON_PROPERTY`, y eso solo ha pasado una vez que
    `_setup_hud()` llama a `icon_font()` — como módulo, construirla al
    importar sería antes de que exista esa fuente.
    """
    kb_lr = ICON_KEYBOARD_LEFT + ICON_KEYBOARD_RIGHT
    return (
        f"{icon_markup(kb_lr)} / {icon_markup(ICON_GAMEPAD_LEFT_RIGHT)}  navegar   -   "
        f"{icon_markup(ICON_KEYBOARD_ENTER)} / {icon_markup(ICON_XBOX_A)}  juego   -   "
        f"{icon_markup(ICON_KEYBOARD_TAB)} / {icon_markup(ICON_GAMEPAD_START)}  scoring   -   "
        f"{icon_markup(ICON_KEYBOARD_X)} / {icon_markup(ICON_XBOX_X)}  filtrar   -   "
        f"{icon_markup(ICON_KEYBOARD_SPACE)} / {icon_markup(ICON_XBOX_Y)}  etiquetas   -   "
        f"{icon_markup(ICON_KEYBOARD_O)} / {icon_markup(ICON_GAMEPAD_L2)}  ocultos   -   "
        f"{icon_markup(ICON_KEYBOARD_ESCAPE)} / {icon_markup(ICON_GAMEPAD_SELECT)}  opciones"
    )


def _menu_hint(extra: str = "") -> str:
    """
    Pista de teclas al pie de un menú: navegar, elegir y volver.

    `extra` se añade al final para los menús con alguna tecla propia (el de
    scoring, que además configura con X).
    """
    kb_ud = ICON_KEYBOARD_UP + ICON_KEYBOARD_DOWN
    hint = (
        f"{icon_markup(kb_ud)} / {icon_markup(ICON_GAMEPAD_UP_DOWN)}  navegar   -   "
        f"{icon_markup(ICON_KEYBOARD_ENTER)} / {icon_markup(ICON_XBOX_A)}  elegir   -   "
        f"{icon_markup(ICON_KEYBOARD_ESCAPE)} / {icon_markup(ICON_XBOX_B)}  volver"
    )
    return f"{hint}   -   {extra}" if extra else hint


class App(ShowBase):
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

        # Para guardar los cambios del menú de juego (terminado, oculto...).
        # Es el mismo repositorio que usa `build_real_entries` para leer, y
        # solo se le piden escrituras de un juego suelto (`save_game`), que
        # tocan la tabla de extras y no el pipeline.
        self.library_repository = LibraryRepository()
        entries = [
            CarouselEntry(
                key=e["key"], title=e["title"], texture=e["texture"],
                stores=e.get("stores", frozenset()), game=e.get("game"),
            )
            for e in raw_entries
        ]
        self.entries = entries
        self.carousel_root = self.render.attach_new_node("carousel-root")
        self.carousel_root.set_z(CAROUSEL_RAISE)
        self.carousel = Carousel(self.carousel_root, entries)

        # Los juegos marcados como ocultos no salen en el carrusel mientras
        # no se pidan expresamente (L2 / tecla "o").
        self._show_hidden = False
        self._apply_hidden_filter()

        # Carátulas que aún no están en disco: se descargan en segundo plano
        # y se sustituyen en caliente cuando llegan (ver _update). Se piden
        # SOLO las de alrededor de la selección, no todas de golpe: con la
        # biblioteca real faltan 1206 de 1273, y encolarlas todas al arrancar
        # es una tormenta de descargas de la que además solo se van a ver
        # nueve. Se van pidiendo a medida que se navega.
        self.cover_loader = CoverLoader()
        self._pending_covers = {
            key: (igdb_id, cover_url) for key, igdb_id, cover_url in pending_downloads
        }

        self._setup_hud()

        # Estado de la navegación mantenida (ver `_update_navigation`) y del
        # fondo diferido (ver `_update_background`).
        self._nav_direction = 0
        self._nav_held_time = 0.0
        self._nav_next_repeat = 0.0
        self._background_key = None
        self._settle_time = 0.0
        self._labels_visible = True
        # Se pone a True en `destroy()`; ver la guarda de `_update`.
        self._shutting_down = False
        # Juego sobre el que se abrió el menú de juego (ver `_open_game_menu`).
        self._game_menu_entry = None
        # Se marca al cambiar "Oculto" y se resuelve al cerrar ese menú.
        self._hidden_filter_dirty = False

        # Antes de `_on_selection_changed`: es quien pone el color de acento
        # de los menús a partir de la tienda del juego elegido, así que los
        # menús tienen que existir ya.
        self._setup_menus()
        self._on_selection_changed()

        self._setup_keyboard()
        self.gamepad = GamepadInput(
            self,
            on_confirm=self._on_confirm,
            on_back=self._on_back,
            on_options=self._open_options_menu,
            on_scoring=self._open_scoring_menu,
            on_filter=self._open_filter_menu,
            on_labels=self._toggle_labels,
            on_hidden=self._toggle_hidden,
        )

        self.task_mgr.add(self._update, "carousel-update")

        # `destroy()` ya existía (cierra `cover_loader` y `gamepad`) pero
        # nada la llamaba: `userExit()` acaba en `sys.exit()` sin pasar por
        # aquí. `ThreadPoolExecutor` no crea hilos daemon, así que el propio
        # intérprete se queda esperando a que sus hilos de descarga acaben
        # antes de poder cerrar el proceso — con carátulas descargándose al
        # arrancar (comportamiento normal, ver `real_data.py`), casi
        # siempre había alguna descarga en curso al cerrar la ventana, y el
        # proceso se quedaba colgado hasta que esa petición HTTP terminara
        # (o para siempre con Ctrl+C). `exitFunc` es el enganche que
        # `ShowBase.userExit()` ya llama antes de `sys.exit()` para
        # exactamente este caso — no hace falta reimplementar el cierre a
        # mano ni engancharse a otro evento.
        self.exitFunc = self.destroy

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
        # Alejada respecto a la primera versión (-8.5) para que el carrusel
        # ocupe menos pantalla mantieniendo las proporciones entre la caja
        # seleccionada y las vecinas (ver CAROUSEL_RAISE para la compensación
        # vertical, así queda a la misma distancia del título que antes).
        self.camera.set_pos(0, -15.3, 0.7)
        self.camera.look_at(0, -3, 0.15)

    def _setup_hud(self) -> None:
        # Una sola carga de fuente para todo el HUD (título, ficha, ayuda);
        # `ui_font()` cachea internamente, así que no hay coste por repetir
        # la llamada en cada widget.
        font = ui_font()
        # Registra ICON_PROPERTY antes de construir la barra de ayuda, que
        # es lo único del HUD que mezcla iconos con texto — ver
        # `_build_help_text()`.
        icon_font()

        self.title_text = OnscreenText(
            text="", pos=(0, TITLE_TEXT_Y), scale=TITLE_TEXT_SCALE,
            fg=(1, 1, 1, 1), align=TextNode.A_center, mayChange=True, font=font,
        )

        # Avisos efímeros, a la altura del título y pegados a la derecha.
        self.notifier = Notifier(self.aspect2d, self.get_aspect_ratio())

        # Ficha a todo lo ancho, independiente del aspect ratio de la
        # ventana: aspect2d reescala X según get_aspect_ratio(), así que el
        # frame debe ir de -aspect a +aspect para tocar los dos bordes.
        # Ojo: aspect_ratio se lee de nuevo en cada resize (_on_window_event)
        # — cachearlo solo aquí lo dejaba desactualizado tras maximizar.
        self.ficha_frame = DirectFrame(
            parent=self.aspect2d,
            frameColor=FICHA_BAR_COLOR,
            frameSize=(-1, 1, -1.0, FICHA_BAR_TOP_Z),
            pos=(0, 0, 0),
        )
        # Estado de la animación de aparecer/desaparecer con los menús (ver
        # `_animate_ficha`). `_ficha_visible` es la posición LÓGICA de
        # destino, no si está a la vista ahora mismo — se necesita para no
        # relanzar la misma animación dos veces si dos menús se abren
        # seguidos sin que la ficha llegue a volver de en medio.
        self._ficha_visible = True
        self._ficha_anim: Parallel | None = None

        # Una fila por campo (etiqueta a la derecha, valor a la izquierda) en
        # vez de un único texto multilínea por columna. Da dos cosas que
        # aquello no daba: interlineado a medida (`FICHA_LINE_HEIGHT`) — el
        # de la fuente va pegado al tamaño de letra y ocho filas seguidas se
        # leen como un bloque macizo, y no se puede cambiar sin tocar la
        # fuente, que es compartida por todo el HUD — y etiqueta más apagada
        # que el dato, que es lo que hace la ficha legible de un vistazo.
        #
        # Las etiquetas se escriben una sola vez: no cambian al navegar.
        self.ficha_label_texts = []
        self.ficha_value_texts = []
        for label in FIELD_LABELS:
            self.ficha_label_texts.append(OnscreenText(
                parent=self.ficha_frame, text=f"{label}:", pos=(0, 0),
                scale=FICHA_LABEL_SCALE, fg=FICHA_LABEL_COLOR,
                align=TextNode.A_right, mayChange=False, font=font,
            ))
            self.ficha_value_texts.append(OnscreenText(
                parent=self.ficha_frame, text="", pos=(0, 0),
                scale=FICHA_LABEL_SCALE, fg=FICHA_VALUE_COLOR,
                align=TextNode.A_left, mayChange=True, font=font,
            ))

        self.description_text = OnscreenText(
            parent=self.ficha_frame, text="", pos=(0, 0),
            scale=DESCRIPTION_TEXT_SCALE, fg=(0.86, 0.86, 0.89, 1),
            align=TextNode.A_left, wordwrap=40, mayChange=True, font=font,
        )
        self.help_text = OnscreenText(
            parent=self.ficha_frame, text=_build_help_text(),
            pos=(0, -0.955), scale=0.032,
            fg=(0.55, 0.55, 0.6, 1), align=TextNode.A_center, mayChange=False,
            font=font,
        )

        self._resize_ficha()

    def _on_window_event(self, window) -> None:
        """
        `ShowBase.__init__` ya se suscribe a "window-event" con su propio
        `windowEvent()` — el que detecta que se ha cerrado la ventana desde
        el gestor de ventanas (la X) y llama a `userExit()`. `self.accept`
        no APILA manejadores por evento: dos `accept` del mismo objeto para
        el mismo evento son el mismo hueco, y el segundo se queda con el
        único sitio, así que suscribirse aquí sin más SUSTITUYE al de
        ShowBase en vez de sumarse — la ventana se cerraba (la caja
        desaparecía) pero el proceso se quedaba corriendo de fondo para
        siempre, porque `userExit()` ya no se llamaba.
        Encadenar explícitamente a `ShowBase.windowEvent` en vez de
        reimplementar el cierre a mano: así se conserva también el resto de
        lo que hace (pausar al minimizar, etc.) sin duplicarlo.

        `getProperties` no existe en modo offscreen (`self.win` es un
        `GraphicsBuffer`, no una `GraphicsWindow` de verdad — mismo caso que
        `request_properties` más arriba en `__init__`), así que se
        comprueba antes de encadenar para no romper los tests/smoke scripts
        que arrancan la app en ese modo.
        """
        if hasattr(window, "getProperties"):
            ShowBase.windowEvent(self, window)
        self._sync_lens_aspect_ratio()
        self._resize_ficha()

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

    def _resize_ficha(self) -> None:
        """
        Recoloca la ficha al ancho actual. Todo lo horizontal se deriva del
        aspect ratio de la ventana, no de constantes fijas: `aspect2d` va de
        -aspect a +aspect en X, así que un layout calculado una sola vez al
        arrancar se descoloca en cuanto se maximiza o se cambia de tamaño.
        """
        aspect = self.get_aspect_ratio()
        self.ficha_frame["frameSize"] = (-aspect, aspect, -1.0, FICHA_BAR_TOP_Z)
        self.notifier.resize(aspect)

        left = -aspect + FICHA_SIDE_MARGIN
        right = aspect - FICHA_SIDE_MARGIN
        available = right - left

        self._ficha_top = FICHA_BAR_TOP_Z - FICHA_TOP_MARGIN
        self._ficha_label_x = left + FICHA_LABEL_COLUMN
        self._ficha_value_x = self._ficha_label_x + FICHA_VALUE_GAP

        fields_right = left + available * FICHA_FIELDS_COLUMN_FRACTION
        # `wordwrap` va en unidades del propio texto (antes de aplicarle su
        # escala), así que el ancho disponible hay que dividirlo por ella.
        value_wrap = max(8.0, (fields_right - self._ficha_value_x) / FICHA_LABEL_SCALE)
        for value_text in self.ficha_value_texts:
            value_text["wordwrap"] = value_wrap

        description_x = fields_right + DESCRIPTION_COLUMN_GAP
        self.description_text.set_pos(description_x, 0, self._ficha_top)
        self.description_text["wordwrap"] = max(
            8.0, (right - description_x) / DESCRIPTION_TEXT_SCALE,
        )

        self._layout_ficha_rows()

    def _layout_ficha_rows(self) -> None:
        """
        Apila las filas de la ficha de arriba abajo, dando a cada una el alto
        que de verdad ocupa su valor.

        No vale con `fila * FICHA_LINE_HEIGHT`: los valores se parten en
        varias líneas (un juego con nueve géneros ocupa tres), y con paso
        fijo las filas siguientes se le montarían encima. El número de
        líneas hay que preguntárselo al TextNode DESPUÉS de asignarle el
        texto, que es quien aplica el ajuste de línea.
        """
        z = self._ficha_top
        for label_text, value_text in zip(self.ficha_label_texts, self.ficha_value_texts):
            # Tres coordenadas, no dos: OnscreenText hereda de NodePath, y
            # su `pos=(x, z)` de dos elementos solo vale en el constructor.
            label_text.set_pos(self._ficha_label_x, 0, z)
            value_text.set_pos(self._ficha_value_x, 0, z)
            rows = max(1, value_text.textNode.get_num_rows())
            z -= rows * FICHA_LINE_HEIGHT

    # ──────────────────────────────
    # Entrada
    # ──────────────────────────────

    def _setup_keyboard(self) -> None:
        # Las flechas se siguen como estado (pulsada / soltada), no como
        # eventos sueltos, para poder repetir mientras se mantengan — ver
        # `_held_direction`. Las cuatro, no solo las horizontales: las
        # verticales navegan los menús con la misma mecánica.
        self._keys_held = dict.fromkeys(("left", "right", "up", "down"), False)
        for key in ("left", "right", "up", "down"):
            self.accept(f"arrow_{key}", self._set_key_held, [key, True])
            self.accept(f"arrow_{key}-up", self._set_key_held, [key, False])

        self.accept("enter", self._on_confirm)
        self.accept("escape", self._on_escape_key)
        self.accept("space", self._toggle_labels)
        self.accept("tab", self._open_scoring_menu)
        self.accept("x", self._on_filter_key)
        self.accept("o", self._toggle_hidden)

    def _set_key_held(self, name: str, held: bool) -> None:
        self._keys_held[name] = held

    def _navigate(self, direction: int) -> None:
        """
        Un paso de navegación.

        En el carrusel es horizontal y en un menú vertical, así que `_update_navigation`
        ya elige de qué eje viene; aquí solo se aplica al que esté al mando.
        """
        menu = self.active_menu
        if menu is not None:
            menu.move_focus(direction)
        else:
            self.carousel.move(direction)
            self._on_selection_changed()

    def _held_direction(self) -> int:
        """
        Dirección que se está pidiendo ahora mismo, de teclado o de mando.

        El eje depende de quién tenga el mando: con un menú abierto se
        navega en VERTICAL y con el carrusel en HORIZONTAL. Antes esto solo
        miraba el eje horizontal y los menús se recorrían con izquierda y
        derecha, que era lo que había cuando lo único que existía era el
        carrusel.

        Se lee como ESTADO en vez de reaccionar a eventos de pulsación,
        porque un evento no dice si la tecla sigue abajo. Se podría usar el
        auto-repeat del sistema (Panda3D emite "arrow_left-repeat"), pero su
        cadencia la fija el escritorio del usuario y no tiene por qué pegar
        con un carrusel; con el estado, el ritmo lo decidimos aquí y sale
        igual en teclado y en mando.
        """
        if self.active_menu is not None:
            direction = (1 if self._keys_held["down"] else 0) - (
                1 if self._keys_held["up"] else 0
            )
            if direction:
                return direction
            return self.gamepad.direction_v() if self.gamepad else 0

        direction = (1 if self._keys_held["right"] else 0) - (
            1 if self._keys_held["left"] else 0
        )
        if direction:
            return direction
        return self.gamepad.direction() if self.gamepad else 0

    def _update_navigation(self, dt: float) -> None:
        direction = self._held_direction()
        in_menu = self.active_menu is not None
        delay = MENU_REPEAT_DELAY if in_menu else NAV_REPEAT_DELAY

        if direction != self._nav_direction:
            self._nav_direction = direction
            self._nav_held_time = 0.0
            self._nav_next_repeat = delay
            if direction:
                self._navigate(direction)
            return

        if not direction:
            return

        self._nav_held_time += dt
        for _ in range(NAV_MAX_STEPS_PER_FRAME):
            if self._nav_held_time < self._nav_next_repeat:
                break
            self._navigate(direction)
            if in_menu:
                # Sin aceleración en los menús: son listas cortas y de
                # longitud fija, así que no hay nada que "recorrer deprisa" —
                # acelerar solo haría pasarse de la opción buscada.
                self._nav_next_repeat += MENU_REPEAT_INTERVAL
                continue
            elapsed = self._nav_held_time - NAV_REPEAT_DELAY
            accel = min(1.0, max(0.0, elapsed / NAV_REPEAT_ACCEL_TIME))
            interval = NAV_REPEAT_INTERVAL + accel * (
                NAV_REPEAT_MIN_INTERVAL - NAV_REPEAT_INTERVAL
            )
            self._nav_next_repeat += interval
        else:
            # Se agotó el tope de pasos por frame: se descarta lo que quede
            # pendiente en vez de arrastrarlo, que si no el retraso se
            # acumula y el carrusel sigue corriendo solo tras soltar.
            self._nav_next_repeat = self._nav_held_time

    def _toggle_labels(self) -> None:
        """Muestra u oculta las etiquetas de todas las cajas (espacio / Y)."""
        self._labels_visible = not self._labels_visible
        self.carousel.set_labels_visible(self._labels_visible)

    def _visible_keys(self) -> set:
        """
        Qué juegos deben verse en el carrusel ahora mismo.

        Único sitio donde se decide, para que el arranque y el interruptor
        de ocultos no puedan discrepar. Cuando se conecten los filtros del
        menú de "Filtrar y ordenar", el resto de condiciones van aquí.
        """
        return {
            entry.key for entry in self.entries
            if self._show_hidden or not (entry.game and entry.game.hidden)
        }

    def _apply_hidden_filter(self) -> None:
        self.carousel.set_visible_keys(self._visible_keys())

    def _toggle_hidden(self) -> None:
        """
        Enseña u oculta los juegos marcados como ocultos (L2 / tecla "o").

        Al volver a mostrarlos, cada uno reaparece en su sitio dentro del
        recorrido, no al final: `Carousel.set_visible_keys` rehace el orden
        a partir de la lista completa.
        """
        self._show_hidden = not self._show_hidden
        self._apply_hidden_filter()
        # La selección puede haber cambiado de juego (si el que estaba
        # delante era justo uno oculto que acaba de desaparecer), así que
        # hay que refrescar ficha, título y fondo.
        self._on_selection_changed()
        self.notifier.show(
            "Mostrando ocultos" if self._show_hidden else "Ocultando juegos"
        )
        logger.info(
            "gui3d: juegos ocultos "
            f"{'visibles' if self._show_hidden else 'escondidos'} "
            f"({self.carousel.visible_count} juegos en el carrusel)"
        )

    # ──────────────────────────────
    # Menús
    # ──────────────────────────────

    def _setup_menus(self) -> None:
        """
        Construye los menús una vez y los deja ocultos.

        Se crean todos al arrancar en vez de bajo demanda porque construir
        uno implica generar geometría y atlas de texto, y hacerlo la primera
        vez que se pulsa el botón se nota como un tirón justo al abrirlo.
        Ocupan poco: son unas pocas decenas de textos en total.
        """
        self._menu_stack: list[Menu] = []

        scoring_hint = _menu_hint(
            f"{icon_markup(ICON_KEYBOARD_X)} / {icon_markup(ICON_XBOX_X)}  configurar"
        )

        self.options_menu = Menu(
            self.aspect2d, menus.OPTIONS_TITLE, menus.OPTIONS_ITEMS, hint=_menu_hint(),
        )
        self.quit_menu = Menu(
            self.aspect2d, menus.QUIT_TITLE, menus.QUIT_ITEMS, hint=_menu_hint(),
        )
        self.scoring_menu = Menu(
            self.aspect2d, menus.SCORING_TITLE, menus.SCORING_ITEMS, hint=scoring_hint,
        )
        self.filter_menu = Menu(
            self.aspect2d, menus.FILTER_TITLE, menus.FILTER_ITEMS, hint=_menu_hint(),
        )
        # Sin elementos todavía: los suyos dependen del juego y se rellenan
        # al abrirlo (ver `_open_game_menu`).
        self.game_menu = Menu(self.aspect2d, "", [], hint=_menu_hint())

    @property
    def active_menu(self) -> Menu | None:
        """El menú que tiene el foco, o None si manda el carrusel."""
        return self._menu_stack[-1] if self._menu_stack else None

    def _push_menu(self, menu: Menu) -> None:
        """
        Abre un menú por encima del que hubiera.

        El de debajo se OCULTA. Se probó a dejarlo visible, para que al
        abrir "Salir" desde Opciones se siguiera viendo de dónde vienes,
        pero todos los menús se dibujan centrados en el mismo sitio: los dos
        paneles quedaban uno encima de otro y los textos se superponían
        letra sobre letra, ilegibles.
        """
        if self.active_menu is None:
            # Primer menú de la pila: es el momento en que la ficha se
            # aparta. Entrar a un submenú desde otro (Salir sobre Opciones)
            # no la vuelve a animar, ya está fuera.
            self._animate_ficha(visible=False)
        else:
            self.active_menu.close()

        self._refresh_menu_accent()
        menu.open()
        self._menu_stack.append(menu)
        # El foco cambia de dueño, así que se corta la repetición en curso:
        # si no, la pulsación que abrió el menú seguiría contando como
        # mantenida y el foco arrancaría ya moviéndose solo.
        self._reset_navigation()

    def _pop_menu(self) -> None:
        """Cierra el menú activo y devuelve el foco (y la vista) al anterior."""
        if not self._menu_stack:
            return
        closed = self._menu_stack.pop()
        closed.close()

        # Si en el menú del juego se ha tocado "Oculto", el filtro se aplica
        # ahora, con el menú ya cerrado (ver `_on_game_flag_toggled`).
        if closed is self.game_menu and self._hidden_filter_dirty:
            self._hidden_filter_dirty = False
            self._apply_hidden_filter()
            self._on_selection_changed()

        if self.active_menu is not None:
            self.active_menu.open()
        else:
            # Se vació la pila: se vuelve al carrusel, así que la ficha
            # deshace la animación y reaparece.
            self._animate_ficha(visible=True)
        self._reset_navigation()

    def _reset_navigation(self) -> None:
        self._nav_direction = 0
        self._nav_held_time = 0.0
        self._nav_next_repeat = 0.0

    def _animate_ficha(self, visible: bool) -> None:
        """
        Aparta la ficha (y la barra de ayuda, que cuelga del mismo frame)
        hacia abajo con un desvanecido a la vez, o deshace el movimiento.

        Deslizar Y desvanecer en paralelo, no una animación de cada tipo por
        separado: `Parallel` los lanza y gestiona como una sola unidad (un
        `finish()` corta las dos), y siguen siendo dos lerps baratos sobre
        UN nodo — nada de geometría ni de texturas de por medio, por eso
        vale como "poco costosa".
        """
        if self._ficha_visible == visible:
            return
        self._ficha_visible = visible

        if self._ficha_anim is not None:
            self._ficha_anim.finish()

        target_z = 0.0 if visible else -FICHA_ANIM_SLIDE
        target_alpha = 1.0 if visible else 0.0
        self._ficha_anim = Parallel(
            LerpPosInterval(
                self.ficha_frame, FICHA_ANIM_DURATION, (0, 0, target_z),
                blendType="easeInOut",
            ),
            LerpColorScaleInterval(
                self.ficha_frame, FICHA_ANIM_DURATION, (1, 1, 1, target_alpha),
                blendType="easeInOut",
            ),
        )
        self._ficha_anim.start()

    def _refresh_menu_accent(self) -> None:
        """
        Pone el color de la tienda del juego actual como color de resaltado
        de todos los menús (el mismo del estuche y del banner de su
        carátula, aclarado para que se lea sobre el panel oscuro).
        """
        entry = self.carousel.selected
        accent = as_text_color(primary_store_color(entry.stores))
        for menu in (
            self.options_menu, self.quit_menu, self.scoring_menu,
            self.filter_menu, self.game_menu,
        ):
            menu.set_accent_color(accent)

    # ── Aperturas ──

    def _open_options_menu(self) -> None:
        """Select / Esc sobre el carrusel."""
        self._push_menu(self.options_menu)

    def _open_scoring_menu(self) -> None:
        """Start / Tab sobre el carrusel."""
        if self.active_menu is None:
            self._push_menu(self.scoring_menu)

    def _open_filter_menu(self) -> None:
        """X sobre el carrusel."""
        if self.active_menu is None:
            self._push_menu(self.filter_menu)

    def _on_filter_key(self) -> None:
        """
        La tecla "x". Dentro del menú de scoring configura el sistema
        enfocado; fuera de cualquier menú, abre el de filtrar y ordenar.
        """
        if self.active_menu is self.scoring_menu:
            self._configure_focused_scoring()
        elif self.active_menu is None:
            self._open_filter_menu()

    def _open_game_menu(self) -> None:
        """A / Enter sobre el carrusel: las opciones del juego seleccionado."""
        entry = self.carousel.selected
        if entry.game is None:
            logger.info("gui3d: el juego seleccionado no tiene ficha, no hay menú")
            return

        self.game_menu.set_title(entry.title)
        self.game_menu.set_items(menus.build_game_items(entry.game))
        # Se recuerda SOBRE QUÉ juego se abrió en vez de volver a mirar
        # `carousel.selected` al marcar una casilla: hoy da igual (con un
        # menú abierto la navegación es suya y la selección no se mueve),
        # pero atarlo aquí evita que un cambio futuro acabe guardando el
        # estado en el juego equivocado, que es un fallo silencioso y feo.
        self._game_menu_entry = entry
        self._push_menu(self.game_menu)

    # ── Acciones ──

    def _on_confirm(self) -> None:
        """A / Enter: elige en el menú activo, o abre el del juego."""
        menu = self.active_menu
        if menu is None:
            self._open_game_menu()
            return

        item = menu.focused_item
        if item is None:
            return

        if item.kind == "check":
            menu.toggle_focused()
            self._on_game_flag_toggled(item)
            return

        self._activate(menu, item.key)

    def _activate(self, menu: Menu, key: str) -> None:
        """
        Qué hace elegir un elemento. De momento casi todo se queda en el
        log: esta pasada es la del sistema de menús y su navegación, y las
        acciones de verdad (ordenar, filtrar, cambiar de scoring) se
        conectan después.
        """
        if key == "quit":
            self._push_menu(self.quit_menu)
        elif key == "quit_yes":
            self.userExit()
        elif key == "quit_no":
            self._pop_menu()
        else:
            logger.info(f"gui3d: elegido {key!r} en el menú {menu.title!r}")

    def _configure_focused_scoring(self) -> None:
        item = self.scoring_menu.focused_item
        if item is not None:
            logger.info(f"gui3d: configurar el scoring {item.key!r} (pendiente)")

    def _on_game_flag_toggled(self, item) -> None:
        """
        Persiste una casilla del menú de juego en la base de datos.

        Se guarda al momento, no al cerrar el menú con un "Guardar": el menú
        se cierra con B, que en el resto de la interfaz significa "volver",
        y si además descartara los cambios sería una trampa.

        Van a `library_cacher` (tabla `user_games` de library.db), NO a
        `save_game()` del repositorio, que fue el primer intento y no
        guardaba nada: ese solo persiste los "extras" (duración, notas de
        Steam...) y los estados del usuario viven en OTRA base de datos a
        propósito — la de extras es caché regenerable y esta no, para que
        borrar la caché no te borre los terminados y los favoritos.

        Se mandan LOS CUATRO estados, no solo el que se acaba de tocar:
        `set_status` reescribe la fila entera (es un UPSERT), así que
        pasarle uno solo pondría los otros tres a False. Es exactamente lo
        que hace la TUI en `gui/app.py:_toggle_game_flag`.
        """
        entry = self._game_menu_entry
        game = entry.game if entry else None
        field = item.payload.get("field")
        if game is None or field is None:
            return

        setattr(game, field, item.checked)
        self.library_repository.library_cacher.set_status(
            game.igdb_id,
            finished=game.finished,
            hidden=game.hidden,
            backlog=game.backlog,
            favorite=game.favorite,
        )
        logger.info(
            f"gui3d: {game.title!r}: {field} = {item.checked}"
        )
        # Las etiquetas de la caja (favorito, terminado, backlog) salen de
        # estos mismos campos, así que hay que redibujarlas para que el
        # cambio se vea al volver al carrusel.
        self.carousel.rebuild_labels(entry.key, game, self._labels_visible)

        if field == "hidden":
            # No se re-filtra aquí mismo: el menú de este juego sigue
            # abierto y quitarle la caja de debajo haría que el carrusel se
            # recolocara y la selección saltara a otro juego mientras lo
            # estás editando. Se apunta y se aplica al cerrar el menú.
            self._hidden_filter_dirty = True

    def _on_back(self) -> None:
        """
        El botón B: vuelve al menú anterior.

        Sobre el carrusel no hace nada a propósito — es "volver", y en la
        pantalla principal no hay a dónde volver. Quien abre Opciones ahí es
        Select (o Esc en el teclado, ver `_on_escape_key`).
        """
        if self._menu_stack:
            self._pop_menu()

    def _on_escape_key(self) -> None:
        """
        La tecla Esc hace de B y de Select a la vez, porque el teclado no
        tiene un equivalente cómodo a los dos: dentro de un menú vuelve, y
        en la pantalla principal abre Opciones.
        """
        if self._menu_stack:
            self._pop_menu()
        else:
            self._open_options_menu()

    # ──────────────────────────────
    # Frame
    # ──────────────────────────────

    def _on_selection_changed(self) -> None:
        """
        Todo lo que hay que rehacer cuando cambia el juego seleccionado.

        El fondo NO se toca aquí: se deja para cuando la navegación pare
        (ver `_update_background`), porque cambiarlo cuesta un desenfoque de
        unos 9 ms y al desplazarse rápido daría un tirón por paso.
        """
        self._settle_time = 0.0
        self._refresh_selection_text()
        self._request_nearby_covers()
        self._refresh_menu_accent()

    def _update_background(self, dt: float) -> None:
        """Pone de fondo la carátula seleccionada, si lleva un rato quieta."""
        self._settle_time += dt
        if self._settle_time < BACKGROUND_SETTLE_DELAY:
            return

        key = self.carousel.selected.key
        texture = self.carousel.selected_texture
        # También hay que reaccionar a que llegue la carátula real de la que
        # ya está seleccionada, no solo a que cambie la selección: de ahí
        # que se compare la textura además de la clave.
        if key != self._background_key or texture is not self.background.current:
            self._background_key = key
            self.background.set_cover(texture)

    def _backfill_covers(self) -> None:
        """
        Va descargando el resto de la biblioteca mientras haya hueco.

        Las de alrededor de la selección ya se piden al navegar; esto es
        para que las demás acaben bajando también en vez de quedarse en el
        color de la tienda para siempre. Se encolan de pocas en pocas
        (`COVER_BACKFILL_INFLIGHT`) justamente para no adelantarse a las que
        se están viendo: si se metieran las 1200 de golpe en la cola, una
        carátula recién pedida por navegación tendría que esperar a que
        terminaran todas las de delante.

        Solo baja ficheros a disco. Convertirlos en textura es cosa de
        `_on_cover_ready`, y solo lo hace con las cercanas.
        """
        for key, (igdb_id, cover_url) in self._pending_covers.items():
            if self.cover_loader.inflight >= COVER_BACKFILL_INFLIGHT:
                return
            self.cover_loader.request(key, igdb_id, cover_url)

    def _is_near_selection(self, key: object) -> bool:
        """¿Está esta caja dentro del radio de precarga de la selección?"""
        return self.carousel.is_near_selection(key, COVER_PRELOAD_RADIUS)

    def _request_nearby_covers(self) -> None:
        """
        Se asegura de que las cajas de alrededor de la selección tengan su
        carátula de verdad, y solo esas.

        Si el fichero ya está en disco se carga aquí mismo (3,4 ms, y solo
        para las que acaban de entrar en el radio); si no, se encarga la
        descarga. El radio es más ancho que `VISIBLE_RADIUS` a propósito,
        para que la carátula llegue antes de que el usuario se plante en esa
        caja.
        """
        if not self._pending_covers:
            return

        # La vecindad la calcula el carrusel: con juegos ocultos filtrados,
        # "las de al lado" no son las contiguas en `self.entries` sino las
        # contiguas en el recorrido visible.
        for entry in self.carousel.neighbour_entries(COVER_PRELOAD_RADIUS):
            pending = self._pending_covers.get(entry.key)
            if pending is None:
                continue

            igdb_id, cover_url = pending
            texture = load_cover_texture(igdb_id, cover_url, allow_download=False)
            if texture is not None:
                self._apply_cover(entry.key, texture)
            else:
                self.cover_loader.request(entry.key, igdb_id, cover_url)

    def _apply_cover(self, key: object, texture) -> None:
        """Pone la carátula real en su caja y la da por resuelta."""
        self._pending_covers.pop(key, None)
        self.carousel.set_texture(key, texture)

    def _on_cover_ready(self, key: object, path) -> None:
        """
        Una carátula acaba de llegar a disco.

        Solo se convierte en textura si su caja está cerca de la selección.
        El relleno de fondo descarga la biblioteca entera, y crear las 1266
        texturas conforme van cayendo devolvería por la puerta de atrás el
        gasto de memoria y de CPU que se quita al arrancar. Las lejanas se
        quedan en disco y ya se cargarán si el usuario llega hasta ellas.
        """
        if key not in self._pending_covers or not self._is_near_selection(key):
            return
        texture = load_cover_texture(*self._pending_covers[key], allow_download=False)
        if texture is not None:
            self._apply_cover(key, texture)

    def _refresh_selection_text(self) -> None:
        entry = self.carousel.selected
        self.title_text.setText(entry.title)

        values = build_values(entry.game) if entry.game else [""] * len(FIELD_LABELS)
        for value_text, value in zip(self.ficha_value_texts, values):
            value_text.setText(value)
        self.description_text.setText(
            build_description(entry.game) if entry.game else ""
        )
        # Recolocar después de escribir: el alto de cada fila depende de en
        # cuántas líneas ha partido su valor, y eso solo se sabe ya escrito.
        self._layout_ficha_rows()

    def _update(self, task):
        # Al cerrar la ventana, `destroy()` desmonta ShowBase (entre otras
        # cosas se lleva por delante `self.win`) pero esta tarea sigue
        # encolada y llega a ejecutarse una vez más antes de que el
        # `sys.exit()` de `userExit()` haga efecto. Sin esta guarda,
        # `_check_lens_aspect_ratio` reventaba con
        # "AttributeError: 'App' object has no attribute 'win'", y esa
        # excepción SUSTITUÍA al SystemExit que estaba saliendo del bucle de
        # tareas: la aplicación acababa cerrándose con un traceback feo en
        # vez de limpiamente.
        if self._shutting_down:
            return task.done

        self._check_lens_aspect_ratio()

        dt = globalClock.get_dt()
        if self.gamepad:
            # Los gatillos son ejes, no botones: no llegan como eventos y hay
            # que sondearlos (ver `GamepadInput.update`).
            self.gamepad.update()
        self._update_navigation(dt)
        self.carousel.update(dt)

        for key, path in self.cover_loader.poll():
            self._on_cover_ready(key, path)

        self._backfill_covers()
        self._update_background(dt)
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
            self._resize_ficha()

    def destroy(self):
        # Antes que nada: corta la tarea de refresco para que no vuelva a
        # entrar mientras se desmonta todo lo que usa (ver `_update`).
        self._shutting_down = True
        self.task_mgr.remove("carousel-update")
        self.cover_loader.shutdown()
        self.gamepad.destroy()
        super().destroy()


def main() -> None:
    resolution = parse_args(sys.argv[1:])
    if resolution is not None:
        width, height = resolution
        load_prc_file_data("", f"win-size {width} {height}")

    app = App()
    app.run()


if __name__ == "__main__":
    main()
