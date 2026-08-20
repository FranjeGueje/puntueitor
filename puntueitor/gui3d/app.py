"""
Frontend 3D de Puntueitor: carrusel de cajas de juego con ficha, navegable
con teclado o mando.

Alternativa a la TUI (`tui/`), no un reemplazo: las dos leen y escriben la
misma biblioteca, y comparten las operaciones en `core/services/`
(`game_actions`, `unknown_actions`, `library_refresh`).

Arrancó siendo solo lectura y ya no lo es: desde aquí se enriquece un juego,
se desconoce, se rescatan desconocidos, se actualiza la biblioteca y se
regenera entera. Todo lo que va a la red ocurre en hilos propios y se recoge
en `_update`, para que el carrusel siga navegable mientras.

Ejecutar con:
    python -m puntueitor.gui3d.app
    python -m puntueitor.gui3d.app --resolution 1920x1080
    python -m puntueitor.gui3d.app --fhd
"""
import argparse
from functools import partial
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
from puntueitor.gui3d.enrichment import EnrichWorker
from puntueitor.gui3d.refresh import (
    DONE,
    ENRICH_ALL,
    GAME,
    MODE_LABELS,
    PROGRESS,
    REGENERATE,
    SOFT,
    UPDATE_EXTRAS,
    RefreshWorker,
)
from puntueitor.gui3d.game_case import make_placeholder_texture
from puntueitor.gui3d.unknowns import ADOPT, SEARCH, STORE, UnknownJob, UnknownWorker
from puntueitor.gui3d.ficha import FIELD_LABELS, build_description, build_values
from puntueitor.gui3d.fonts import (
    ICON_GAMEPAD_L1,
    ICON_GAMEPAD_R3,
    ICON_GAMEPAD_RSTICK_DOWN,
    ICON_GAMEPAD_RSTICK_LEFT,
    ICON_GAMEPAD_RSTICK_RIGHT,
    ICON_GAMEPAD_RSTICK_UP,
    ICON_GAMEPAD_L2,
    ICON_GAMEPAD_LEFT_RIGHT,
    ICON_GAMEPAD_R1,
    ICON_GAMEPAD_SELECT,
    ICON_GAMEPAD_R2,
    ICON_GAMEPAD_START,
    ICON_GAMEPAD_UP_DOWN,
    ICON_KEYBOARD_DOWN,
    ICON_KEYBOARD_ENTER,
    ICON_KEYBOARD_ESCAPE,
    ICON_KEYBOARD_LEFT,
    ICON_KEYBOARD_O,
    ICON_KEYBOARD_Q,
    ICON_KEYBOARD_R,
    ICON_KEYBOARD_RIGHT,
    ICON_KEYBOARD_SPACE,
    ICON_KEYBOARD_TAB,
    ICON_KEYBOARD_UP,
    ICON_KEYBOARD_W,
    ICON_KEYBOARD_X,
    ICON_XBOX_A,
    ICON_XBOX_B,
    ICON_XBOX_X,
    ICON_XBOX_Y,
    icon_font,
    icon_markup,
    ui_font,
)
from puntueitor.core import paths
from puntueitor.core.diagnostics import describe_error
from puntueitor.core.logging_setup import setup_logging
from puntueitor.core.repository.library_repository import (
    EXTRA_FIELDS,
    LibraryRepository,
)
from puntueitor.core.config import DEFAULT_AVAILABLE_HOURS, ConfigManager
from puntueitor.core.models import Stores
from puntueitor.core.services import unknown_actions
from puntueitor.core.services.game_actions import forget_game
from puntueitor.core.services.library_ops import active_stores, is_in_active_stores
from puntueitor.gui3d import accounts_ui, backup_ui, editor_ui, menus, scoring_ui, state
from puntueitor.gui3d.audio import Audio
from puntueitor.gui3d.filters import (
    TRISTATE_LABELS,
    Filters,
    cycle_tristate,
    parse_duration,
)
from puntueitor.gui3d.gamepad_input import GamepadInput
from puntueitor.gui3d.menu import Menu
from puntueitor.gui3d.notifications import Notifier
from puntueitor.gui3d.text_prompt import TextPrompt
from puntueitor.gui3d.real_data import build_real_entries
from puntueitor.gui3d.sample_data import build_sample_entries
from puntueitor.gui3d import sorting
from puntueitor.gui3d.store_colors import as_text_color, primary_store_color

# El logging NO se configura aquí: hacerlo al importar es lo que dejaba al
# carrusel escribiendo solo a stderr y sin fichero. Lo monta `main()` con
# `setup_logging`, después de la migración de rutas.
logger = logging.getLogger(__name__)

WINDOW_TITLE = "Puntueitor 3D"
TITLE_TEXT_SCALE = 0.09
TITLE_TEXT_Y = 0.90

# Estado de la actualización de la biblioteca: debajo de los avisos, que van a
# la altura del título, para que puedan convivir sin pisarse.
REFRESH_TEXT_Z = TITLE_TEXT_Y - 0.09
REFRESH_TEXT_SCALE = 0.038
REFRESH_TEXT_COLOR = (0.72, 0.78, 0.92, 1)
REFRESH_SIDE_MARGIN = 0.06

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

# Descripción del sistema de scoring, en la misma franja que la ficha.
SCORING_TITLE_SCALE = 0.045
SCORING_DESC_SCALE = 0.036
SCORING_TITLE_TOP_MARGIN = 0.06
SCORING_DESC_GAP = 0.055
SCORING_SIDE_MARGIN = 0.10

# Cuánto se sube el menú de scoring para que su panel quede por encima de la
# franja de descripción (que arranca en FICHA_BAR_TOP_Z).
SCORING_MENU_CENTER_Z = 0.26

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

# Los dos únicos datos que se saben de un juego desconocido: de qué tienda
# viene y con qué identificador. Es justo lo que hace falta para reconocerlo
# y para buscarlo a mano si la identificación automática no acierta.
UNKNOWN_FIELD_LABELS = ("Tienda", "ID")

# Cajas negras: un desconocido no tiene ficha en IGDB y por tanto tampoco
# carátula, así que la caja hace de pizarra para su título. No negro puro —
# 0.02 deja ver el canto del estuche contra el fondo, que también es oscuro.
UNKNOWN_BODY_COLOR = (0.02, 0.02, 0.02)
UNKNOWN_COVER_COLOR = (0.05, 0.05, 0.06)

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
#
# La cadencia se bajó tras probarla con mando: iba a 8 juegos por segundo de
# salida y llegaba a 22, y con eso pasarse del juego que buscas es lo normal,
# no la excepción. Ahora sale a 5 y sube a 12,5 tras dos segundos aguantando.
# Cruzar la biblioteca entera no es cosa de esto: para eso están el salto de
# grupo (L1/R1) y volver al principio (L3).
NAV_REPEAT_DELAY = 0.40
NAV_REPEAT_INTERVAL = 0.20
NAV_REPEAT_MIN_INTERVAL = 0.08
NAV_REPEAT_ACCEL_TIME = 2.0

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

# Cadencia al mantener izquierda/derecha sobre un número (pesos, horas). Más
# rápida que la de navegar: cambiar un peso de 40 a 60 son veinte pasos, y al
# ritmo de recorrer una lista se haría eterno.
MENU_VALUE_REPEAT_INTERVAL = 0.07

#: Nombre de la tarea que devuelve los atajos de teclado tras cerrar el
#: cuadro de texto (ver `App._close_text_prompt`).
_REBIND_TASK = "rebind-shortcuts"

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
    kb_qw = ICON_KEYBOARD_Q + ICON_KEYBOARD_W
    pad_lr = ICON_GAMEPAD_L1 + ICON_GAMEPAD_R1
    return (
        f"{icon_markup(kb_lr)} / {icon_markup(ICON_GAMEPAD_LEFT_RIGHT)}  navegar   -   "
        f"{icon_markup(kb_qw)} / {icon_markup(pad_lr)}  saltar   -   "
        f"{icon_markup(ICON_KEYBOARD_ENTER)} / {icon_markup(ICON_XBOX_A)}  juego   -   "
        f"{icon_markup(ICON_KEYBOARD_TAB)} / {icon_markup(ICON_GAMEPAD_START)}  scoring   -   "
        f"{icon_markup(ICON_KEYBOARD_X)} / {icon_markup(ICON_XBOX_X)}  filtrar   -   "
        f"{icon_markup(ICON_KEYBOARD_SPACE)} / {icon_markup(ICON_XBOX_Y)}  etiquetas   -   "
        f"{icon_markup(ICON_KEYBOARD_O)} / {icon_markup(ICON_GAMEPAD_L2)}  ocultos   -   "
        f"{icon_markup(ICON_KEYBOARD_R)} / {icon_markup(ICON_GAMEPAD_R2)}  actualizar   -   "
        f"{icon_markup(ICON_KEYBOARD_ESCAPE)} / {icon_markup(ICON_GAMEPAD_SELECT)}  opciones"
    )


def _store_set(store: str) -> frozenset:
    """
    La tienda de un desconocido, como el conjunto que espera el carrusel.

    `unknown_games` guarda el nombre en texto, y el banner y los colores
    trabajan con el enum: una tienda que el enum no conozca (o un valor
    corrupto en la base de datos) daría un `ValueError` en mitad del
    arranque del modo, así que se cae a "sin tienda", que ya está
    contemplado (`primary_store_color` tiene su color por defecto).
    """
    try:
        return frozenset({Stores(store)})
    except ValueError:
        logger.warning(f"gui3d: tienda desconocida {store!r} en unknown_games")
        return frozenset()


def _build_unknown_help_text() -> str:
    """
    La barra de ayuda del modo desconocidos.

    Es un texto aparte, en su propio widget, y no una reescritura de la
    normal: `help_text` se creó con `mayChange=False` (nunca cambia mientras
    recorres la biblioteca) y ponerlo a True encarece cada frame de todas
    las sesiones por un modo en el que casi no se entra.
    """
    kb_lr = ICON_KEYBOARD_LEFT + ICON_KEYBOARD_RIGHT
    return (
        f"{icon_markup(kb_lr)} / {icon_markup(ICON_GAMEPAD_LEFT_RIGHT)}  navegar   -   "
        f"{icon_markup(ICON_KEYBOARD_ENTER)} / {icon_markup(ICON_XBOX_A)}  identificar   -   "
        f"{icon_markup(ICON_KEYBOARD_DOWN)} / {icon_markup(ICON_XBOX_B)}  volver a la biblioteca"
    )


def _build_editor_help_text() -> str:
    """
    La barra del Editor Rápido: las cuatro direcciones del stick derecho y
    cómo salir.

    Texto aparte, como el del modo desconocidos, y por el mismo motivo:
    `help_text` se creó con `mayChange=False` porque no cambia nunca mientras
    recorres la biblioteca, y ponerlo a True encarecería cada frame de todas
    las sesiones por un modo en el que se entra a ratos.
    """
    kb_lr = ICON_KEYBOARD_LEFT + ICON_KEYBOARD_RIGHT
    return (
        f"EDITOR RÁPIDO   -   "
        f"{icon_markup(kb_lr)} / {icon_markup(ICON_GAMEPAD_LEFT_RIGHT)}"
        f"  navegar   -   "
        f"I / {icon_markup(ICON_GAMEPAD_RSTICK_UP)}  pendiente   -   "
        f"K / {icon_markup(ICON_GAMEPAD_RSTICK_DOWN)}  terminado   -   "
        f"J / {icon_markup(ICON_GAMEPAD_RSTICK_LEFT)}  ocultar   -   "
        f"L / {icon_markup(ICON_GAMEPAD_RSTICK_RIGHT)}  favorito   -   "
        f"E / {icon_markup(ICON_GAMEPAD_R3)}  salir"
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


def _prompt_hint() -> str:
    """
    Pista del cuadro de texto: pegar, aceptar y cancelar.

    Pegar va PRIMERO a propósito. Es lo que la mayoría viene a hacer aquí
    —el login de las tiendas acaba pegando una URL enorme— y es lo único de
    los tres que no se adivina.

    No hay icono de tecla "V" en la fuente, así que ese lado va como texto.
    """
    return (
        f"Ctrl+V / {icon_markup(ICON_XBOX_X)}  pegar   -   "
        f"{icon_markup(ICON_KEYBOARD_ENTER)} / {icon_markup(ICON_XBOX_A)}  aceptar   -   "
        f"{icon_markup(ICON_KEYBOARD_ESCAPE)} / {icon_markup(ICON_XBOX_B)}  cancelar"
    )


def _value_menu_hint() -> str:
    """
    La de los menús con valores que se cambian con izquierda/derecha: el de
    filtros (N/A, Sí, No) y el de configuración del scoring (los pesos y las
    horas, que suben y bajan de uno en uno).
    """
    kb_lr = ICON_KEYBOARD_LEFT + ICON_KEYBOARD_RIGHT
    return _menu_hint(
        f"{icon_markup(kb_lr)} / {icon_markup(ICON_GAMEPAD_LEFT_RIGHT)}  cambiar"
    )


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

        reales = build_real_entries()
        #: Si el carrusel está enseñando los seis juegos de mentira porque no
        #: hay biblioteca. Mantiene una invariante que vale la pena tener
        #: clara: cuando está puesto, en el carrusel NO HAY NADA MÁS que
        #: ejemplos, y por eso `_on_game_refreshed` puede vaciarlo entero sin
        #: mirar qué había.
        self._sample_mode = reales is None
        raw_entries, pending_downloads = reales or build_sample_entries()

        # Para guardar los cambios del menú de juego (terminado, oculto...).
        # Es el mismo repositorio que usa `build_real_entries` para leer, y
        # solo se le piden escrituras de un juego suelto (`save_game`), que
        # tocan la tabla de extras y no el pipeline.
        self.library_repository = LibraryRepository()
        # Antes del carrusel: de aquí sale qué nota se pinta en las cajas,
        # y las etiquetas se construyen al crearlas.
        self.prefs = state.load_preferences()
        self._build_carousel(raw_entries, pending_downloads)

        # Los juegos marcados como ocultos no salen en el carrusel mientras
        # no se pidan expresamente (L2 / tecla "o").
        self._show_hidden = False
        self._sort_criterion = sorting.CRITERIA[sorting.DEFAULT_CRITERION]
        self._groups: list = []
        # Recuperados de gui3d.json, salvo que se haya pedido no hacerlo en
        # Opciones -> Puntueitor3D. Lo guardado NO se borra al desactivarlo: sigue
        # ahí y vuelve si se reactiva.
        self.filters = (
            state.load_filters() if self.prefs.remember_filters else Filters()
        )
        self._apply_order()

        # Carátulas que aún no están en disco: se descargan en segundo plano
        # y se sustituyen en caliente cuando llegan (ver _update). Se piden
        # SOLO las de alrededor de la selección, no todas de golpe: con la
        # biblioteca real faltan 1206 de 1273, y encolarlas todas al arrancar
        # es una tormenta de descargas de la que además solo se van a ver
        # nueve. Se van pidiendo a medida que se navega.
        self.cover_loader = CoverLoader()
        # Enriquecer un juego va a la red y tarda varios segundos, así que
        # también se hace en su propio hilo y se recoge en `_update`.
        self.enrich_worker = EnrichWorker(self.library_repository)
        # Y actualizar la biblioteca entera, minutos.
        self.refresh_worker = RefreshWorker(self.library_repository)
        # Cuántas cajas ha metido de verdad el trabajo en curso.
        self._refresh_added = 0

        self._setup_hud()

        # Estado de la navegación mantenida (ver `_update_navigation`) y del
        # fondo diferido (ver `_update_background`).
        self._nav_direction = 0
        self._nav_held_time = 0.0
        self._nav_next_repeat = 0.0
        # Estado horizontal dentro de un menú, para detectar el flanco y la
        # repetición al cambiar valores (ver `_update_menu_cycle`).
        self._menu_h_direction = 0
        self._menu_h_held_time = 0.0
        self._menu_h_next_repeat = 0.0
        self._background_key = None
        self._settle_time = 0.0
        self._labels_visible = True
        # Se pone a True en `destroy()`; ver la guarda de `_update`.
        self._shutting_down = False
        # Juego sobre el que se abrió el menú de juego (ver `_open_game_menu`).
        self._game_menu_entry = None
        # Se marca al cambiar "Oculto" y se resuelve al cerrar ese menú.
        self._hidden_filter_dirty = False
        # Qué se ejecuta si se contesta "Sí" en `confirm_menu`. None = no
        # hay ninguna confirmación en curso (ver `_ask_confirm`).
        self._confirm_action = None

        # Modo desconocidos (arriba sobre el carrusel). El carrusel y su
        # hilo se construyen la primera vez que se entra, no al arrancar:
        # son 48 cajas más y un hilo que la mayoría de sesiones no usa.
        self._unknown_mode = False
        self._unknown_carousel = None
        self._unknown_root = None
        self._unknown_entries: list[CarouselEntry] = []
        self.unknown_worker = None
        # Último valor del eje vertical, para disparar solo en el flanco.
        self._mode_v_direction = 0

        # Editor Rápido (R3 o "e"): el stick derecho marca los estados del
        # juego seleccionado sin abrir su menú. `_editor_stick` guarda la
        # última posición leída, otra vez para disparar solo en el flanco.
        self._editor_mode = False
        self._editor_stick = (0, 0)
        # Sobre qué desconocido se está buscando o adoptando ahora mismo.
        self._unknown_job_target = None
        # Sistema de scoring que se está configurando y sus valores en
        # edición (ver `_open_scoring_config`).
        self._config_scorer = None
        self._config_weights: dict[str, float] = {}
        self._config_hours: float = DEFAULT_AVAILABLE_HOURS
        self._config_genres: set[str] = set()
        # Valores en edición del menú de configuración de la aplicación.
        self._settings: dict = {}

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
            # `_on_filter_key`, no `_open_filter_menu`: es el que sabe que
            # dentro del menú de scoring X configura en vez de abrir filtros.
            # Estaba puesto el segundo, así que el botón X del mando abría
            # filtros incluso sobre la lista de sistemas y solo la tecla "x"
            # del teclado configuraba.
            on_filter=self._on_filter_key,
            on_labels=self._toggle_labels,
            on_hidden=self._toggle_hidden,
            on_refresh=self._refresh_library,
            on_jump_start=self._jump_start,
            on_jump=self._jump_group,
            on_editor=partial(editor_ui.toggle_editor_mode, self),
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

        # Sonido. Los ficheros los pone el usuario en su carpeta de
        # configuración y puede que no haya ninguno: `Audio` se encarga de
        # que eso no se note más que en el log (ver `audio.py`).
        self.audio = Audio(
            self.loader,
            sfx_manager=self.sfxManagerList[0] if self.sfxManagerList else None,
            music_manager=self.musicManager,
        )
        self.audio.set_volumes(self.prefs.music_volume, self.prefs.sfx_volume)
        self.audio.start_music(self.prefs.music_volume)

        # Y justo debajo, el estado de la actualización de la biblioteca.
        # No se usa el avisador: el suyo es un mensaje de usar y tirar que se
        # desvanece a los cuatro segundos, y esto tiene que quedarse puesto
        # los minutos que dure. Va en la esquina libre, sin tapar ni la ficha
        # ni la barra de ayuda, y el carrusel se sigue pudiendo navegar.
        self.refresh_text = OnscreenText(
            text="", scale=REFRESH_TEXT_SCALE, fg=REFRESH_TEXT_COLOR,
            align=TextNode.A_right, mayChange=True, font=font,
        )
        self.refresh_text.hide()

        # Descripción del sistema de scoring enfocado. Ocupa la MISMA franja
        # que la ficha del juego, que está apartada mientras hay un menú
        # abierto (ver `_animate_ficha`), así que no se pisan nunca.
        self.scoring_frame = DirectFrame(
            parent=self.aspect2d,
            frameColor=FICHA_BAR_COLOR,
            frameSize=(-1, 1, -1.0, FICHA_BAR_TOP_Z),
            pos=(0, 0, 0),
        )
        self.scoring_frame.hide()
        self.scoring_title_text = OnscreenText(
            parent=self.scoring_frame, text="", pos=(0, 0),
            scale=SCORING_TITLE_SCALE, fg=(0.6, 0.8, 1, 1),
            align=TextNode.A_center, mayChange=True, font=font,
        )
        self.scoring_desc_text = OnscreenText(
            parent=self.scoring_frame, text="", pos=(0, 0),
            scale=SCORING_DESC_SCALE, fg=(0.88, 0.88, 0.91, 1),
            align=TextNode.A_left, wordwrap=40, mayChange=True, font=font,
        )

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
        # La del Editor Rápido, en el mismo sitio y oculta: se turnan.
        self.editor_help_text = OnscreenText(
            parent=self.ficha_frame, text=_build_editor_help_text(),
            pos=(0, -0.955), scale=0.032,
            fg=(0.55, 0.55, 0.6, 1), align=TextNode.A_center, mayChange=False,
            font=font,
        )
        self.editor_help_text.hide()

        self._setup_unknown_hud(font)
        self._resize_ficha()

    def _setup_unknown_hud(self, font) -> None:
        """
        La franja del modo desconocidos: de qué tienda viene, con qué id, y
        por dónde vas.

        Frame aparte en la misma banda, como `scoring_frame`, en vez de
        reescribir la ficha: sus etiquetas son ocho y se crearon con
        `mayChange=False` porque no cambian nunca. Aquí solo hay tres datos,
        y de paso este frame se trae su propia barra de ayuda, que si no
        habría que hacer variable la de la biblioteca por lo mismo.
        """
        self.unknown_frame = DirectFrame(
            parent=self.aspect2d,
            frameColor=FICHA_BAR_COLOR,
            frameSize=(-1, 1, -1.0, FICHA_BAR_TOP_Z),
            pos=(0, 0, 0),
        )
        self.unknown_frame.hide()

        self.unknown_label_texts = []
        self.unknown_value_texts = []
        for label in UNKNOWN_FIELD_LABELS:
            self.unknown_label_texts.append(OnscreenText(
                parent=self.unknown_frame, text=f"{label}:", pos=(0, 0),
                scale=FICHA_LABEL_SCALE, fg=FICHA_LABEL_COLOR,
                align=TextNode.A_right, mayChange=False, font=font,
            ))
            self.unknown_value_texts.append(OnscreenText(
                parent=self.unknown_frame, text="", pos=(0, 0),
                scale=FICHA_LABEL_SCALE, fg=FICHA_VALUE_COLOR,
                align=TextNode.A_left, mayChange=True, font=font,
            ))

        self.unknown_count_text = OnscreenText(
            parent=self.unknown_frame, text="", pos=(0, 0),
            scale=FICHA_LABEL_SCALE, fg=FICHA_LABEL_COLOR,
            align=TextNode.A_left, mayChange=True, font=font,
        )
        self.unknown_help_text = OnscreenText(
            parent=self.unknown_frame, text=_build_unknown_help_text(),
            pos=(0, -0.955), scale=0.032,
            fg=(0.55, 0.55, 0.6, 1), align=TextNode.A_center, mayChange=False,
            font=font,
        )

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
        self.refresh_text.set_pos(
            aspect - REFRESH_SIDE_MARGIN, 0, REFRESH_TEXT_Z,
        )

        # La franja de la descripción del scoring comparte sitio con la ficha
        # y se recoloca igual.
        self.scoring_frame["frameSize"] = (-aspect, aspect, -1.0, FICHA_BAR_TOP_Z)
        # Y la del modo desconocidos, por lo mismo.
        self.unknown_frame["frameSize"] = (-aspect, aspect, -1.0, FICHA_BAR_TOP_Z)
        self._layout_unknown_rows(aspect)
        top = FICHA_BAR_TOP_Z - SCORING_TITLE_TOP_MARGIN
        self.scoring_title_text.set_pos(0, 0, top)
        desc_x = -aspect + SCORING_SIDE_MARGIN
        self.scoring_desc_text.set_pos(desc_x, 0, top - SCORING_DESC_GAP)
        self.scoring_desc_text["wordwrap"] = max(
            8.0, (2 * aspect - 2 * SCORING_SIDE_MARGIN) / SCORING_DESC_SCALE,
        )

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

    def _layout_unknown_rows(self, aspect: float) -> None:
        """
        Coloca las filas del modo desconocidos, con el mismo encaje que la
        ficha para que al cambiar de modo el ojo no tenga que recolocarse.

        Son datos de una línea (una tienda, un identificador), así que aquí
        sí vale el paso fijo que la ficha no puede usar.
        """
        label_x = -aspect + FICHA_SIDE_MARGIN + FICHA_LABEL_COLUMN
        value_x = label_x + FICHA_VALUE_GAP
        z = FICHA_BAR_TOP_Z - FICHA_TOP_MARGIN
        for label_text, value_text in zip(
            self.unknown_label_texts, self.unknown_value_texts,
        ):
            label_text.set_pos(label_x, 0, z)
            value_text.set_pos(value_x, 0, z)
            z -= FICHA_LINE_HEIGHT
        # Separado del par de datos por una fila en blanco: es de otra cosa
        # (dónde estás en la lista, no qué juego es).
        self.unknown_count_text.set_pos(value_x, 0, z - FICHA_LINE_HEIGHT)

    # ──────────────────────────────
    # Entrada
    # ──────────────────────────────

    def _setup_keyboard(self) -> None:
        # Las flechas se siguen como estado (pulsada / soltada), no como
        # eventos sueltos, para poder repetir mientras se mantengan — ver
        # `_held_direction`. Las cuatro, no solo las horizontales: las
        # verticales navegan los menús con la misma mecánica.
        self._keys_held = dict.fromkeys(("left", "right", "up", "down"), False)

        # En una tabla, y no sueltos, porque hay que poder soltarlos TODOS a
        # la vez: mientras se escribe en un cuadro de texto, teclas como "o"
        # o "x" son letras, no atajos. Ver `_bind_shortcuts`.
        self._shortcuts = {
            "enter": (self._on_confirm, []),
            "escape": (self._on_escape_key, []),
            "space": (self._toggle_labels, []),
            "tab": (self._open_scoring_menu, []),
            "x": (self._on_filter_key, []),
            "o": (self._toggle_hidden, []),
            "r": (self._refresh_library, []),
            "q": (self._jump_group, [-1]),
            "w": (self._jump_group, [1]),
            "home": (self._jump_start, []),
            "e": (partial(editor_ui.toggle_editor_mode, self), []),
        }
        # Las cuatro del Editor Rápido, en la misma tabla para que se suelten
        # solas al abrir un cuadro de texto: ahí son letras que se escriben.
        for tecla, direccion in menus.EDITOR_KEYS.items():
            self._shortcuts[tecla] = (partial(editor_ui.editor_gesture, self), [direccion])
        self._bind_shortcuts()

    def _bind_shortcuts(self) -> None:
        """Activa los atajos de teclado y el seguimiento de las flechas."""
        for key in ("left", "right", "up", "down"):
            self.accept(f"arrow_{key}", self._set_key_held, [key, True])
            self.accept(f"arrow_{key}-up", self._set_key_held, [key, False])
        for key, (handler, args) in self._shortcuts.items():
            self.accept(key, handler, args)

    def _release_shortcuts(self) -> None:
        """
        Suelta los atajos para que el teclado sea solo texto.

        Hace falta de verdad: un `DirectEntry` con el foco NO impide que
        Panda3D siga repartiendo los eventos de tecla por el messenger
        (comprobado), así que sin esto escribir "o" en el filtro de nombre
        conmutaría además los juegos ocultos, y "x" abriría un menú encima.
        Las flechas también se sueltan, porque dentro del cuadro de texto
        mueven el cursor.
        """
        for key in ("left", "right", "up", "down"):
            self.ignore(f"arrow_{key}")
            self.ignore(f"arrow_{key}-up")
        for key in self._shortcuts:
            # Esc se queda: no es un carácter que se pueda escribir y es la
            # forma de cancelar el cuadro (`_on_escape_key` lo detecta).
            # Enter sí se suelta, y a propósito: lo recoge el `DirectEntry`,
            # que llama a su `command`. Dejándolo puesto se dispararían los
            # dos y el texto se aplicaría dos veces.
            if key != "escape":
                self.ignore(key)
        # Si alguna flecha se quedó "pulsada" al abrir el cuadro, su evento
        # de soltar ya no va a llegar: se limpia para que el carrusel no
        # arranque solo al volver.
        self._keys_held = dict.fromkeys(self._keys_held, False)
        self._reset_navigation()

    def _set_key_held(self, name: str, held: bool) -> None:
        self._keys_held[name] = held

    def _navigate(self, direction: int) -> None:
        """
        Un paso de navegación.

        En el carrusel es horizontal y en un menú vertical, así que `_update_navigation`
        ya elige de qué eje viene; aquí solo se aplica al que esté al mando.
        """
        # Aquí y no en `Menu.move_focus`: por este método pasan las dos
        # formas de moverse —foco de menú y giro del carrusel—, de teclado y
        # de mando, tanto la pulsación suelta como la repetición mantenida.
        # `play_move` trae su propio freno para la repetición rápida.
        self.audio.play_move()

        menu = self.active_menu
        if menu is not None:
            menu.move_focus(direction)
            if menu is self.scoring_menu:
                # La descripción sigue al foco, como en la TUI.
                scoring_ui.refresh_scoring_description(self)
        else:
            self.active_carousel.move(direction)
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
        # Escribiendo no se navega: el teclado está escribiendo, pero el
        # stick del mando seguiría moviendo el carrusel por detrás.
        if self._typing:
            return 0

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

    def _menu_horizontal(self) -> int:
        """Izquierda/derecha dentro de un menú, para los valores que rotan."""
        if self._typing or self.active_menu is None:
            return 0
        direction = (1 if self._keys_held["right"] else 0) - (
            1 if self._keys_held["left"] else 0
        )
        if direction:
            return direction
        return self.gamepad.direction() if self.gamepad else 0

    def _update_menu_cycle(self, dt: float) -> None:
        """
        Izquierda/derecha dentro de un menú: cambia el valor enfocado.

        Se sondea en vez de reaccionar al evento de tecla para que el mando y
        el teclado sigan el mismo camino. El primer cambio va por FLANCO
        (una pulsación, un cambio) y solo los valores numéricos siguen
        repitiendo si se mantiene — ver `_focused_repeats`.
        """
        direction = self._menu_horizontal()

        if direction != self._menu_h_direction:
            self._menu_h_direction = direction
            self._menu_h_next_repeat = MENU_REPEAT_DELAY
            self._menu_h_held_time = 0.0
            if direction:
                self._adjust_focused(direction)
            return

        if not direction or not self._focused_repeats():
            return

        self._menu_h_held_time += dt
        while self._menu_h_held_time >= self._menu_h_next_repeat:
            self._adjust_focused(direction)
            self._menu_h_next_repeat += MENU_VALUE_REPEAT_INTERVAL

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
        if self._typing or self._blocked_in_unknown_mode("Etiquetas"):
            return
        self._labels_visible = not self._labels_visible
        self.carousel.set_labels_visible(self._labels_visible)

    def _visible_entries(self) -> list:
        """
        Qué juegos deben verse en el carrusel ahora mismo.

        Único sitio donde se decide, para que el arranque, el interruptor de
        ocultos, los filtros y las tiendas marcadas no puedan discrepar.

        Las tiendas se leen UNA vez y no por juego: `ConfigManager` es un
        singleton, pero preguntárselo 1266 veces por cada reordenación solo
        es gratis en apariencia.
        """
        activas = active_stores()
        return [
            entry for entry in self.entries
            if (self._show_hidden or not (entry.game and entry.game.hidden))
            and self.filters.matches(entry.game)
            and is_in_active_stores(entry.game, activas)
        ]

    def _apply_order(self, reset_selection: bool = False) -> None:
        """
        Recalcula filtro + ordenación y se los pasa al carrusel.

        Los dos van juntos y en este orden: primero se decide qué juegos
        entran y luego se ordenan solo esos. Al revés daría lo mismo, pero
        ordenar la biblioteca entera para tirar después la mitad es trabajo
        de más.

        `self._groups` se guarda porque hace falta después para saber en qué
        grupo está la selección al saltar con L1/R1 (ver `_jump_group`).
        """
        criterion = self._sort_criterion
        keys, groups = sorting.order_entries(self._visible_entries(), criterion)
        self._groups = groups
        self.carousel.set_order(keys, groups, reset_selection=reset_selection)

    def _apply_hidden_filter(self) -> None:
        self._apply_order()

    def _toggle_hidden(self) -> None:
        """
        Enseña u oculta los juegos marcados como ocultos (L2 / tecla "o").

        Al volver a mostrarlos, cada uno reaparece en su sitio dentro del
        recorrido, no al final: `_apply_order` rehace filtro y ordenación
        enteros a partir de la lista completa.
        """
        if self._typing or self._blocked_in_unknown_mode("Ocultos"):
            return
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
        # Con qué botón se abrió el menú de la base de la pila: pulsarlo otra
        # vez cierra todo (ver `_toggle_root_menu`).
        self._menu_opener: str | None = None

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
            self.aspect2d, menus.SCORING_TITLE, menus.build_scoring_items(),
            hint=scoring_hint,
        )
        # Subido para dejar sitio a la franja de descripción de abajo, que
        # empieza en `FICHA_BAR_TOP_Z`; centrado se le montaba encima.
        self.scoring_menu.set_center_z(SCORING_MENU_CENTER_Z)
        # Se rellena al abrirlo: sus opciones dependen del sistema elegido.
        self.scoring_config_menu = Menu(
            self.aspect2d, "", [], hint=_value_menu_hint(),
        )
        # Sin elementos todavía: enseñan los valores de los filtros, que
        # cambian, así que se rellenan al abrirlo (ver `_open_filter_menu`).
        self.filter_menu = Menu(
            self.aspect2d, menus.FILTER_TITLE, [], hint=_value_menu_hint(),
        )
        self.text_prompt = TextPrompt(self.aspect2d)
        # Sin elementos todavía: los suyos dependen del juego y se rellenan
        # al abrirlo (ver `_open_game_menu`).
        self.game_menu = Menu(self.aspect2d, "", [], hint=_menu_hint())
        # Ídem: enseña los valores guardados, que cambian.
        self.settings_menu = Menu(
            self.aspect2d, menus.SETTINGS_TITLE, [], hint=_menu_hint(),
        )
        # Credenciales y sesiones, lo primero que hay que rellenar.
        self.accounts_menu = Menu(
            self.aspect2d, menus.ACCOUNTS_TITLE, [], hint=_menu_hint(),
        )
        # Sus dos ajustes se cambian con izquierda/derecha, así que lleva la
        # pista que lo menciona.
        self.gui3d_menu = Menu(
            self.aspect2d, menus.GUI3D_TITLE, [], hint=_value_menu_hint(),
        )
        # Uno solo para todas las preguntas de sí/no sobre el juego: título
        # e items se rehacen en cada apertura (ver `_ask_confirm`). El de
        # salir se queda aparte porque es fijo y no va sobre ningún juego.
        self.confirm_menu = Menu(self.aspect2d, "", [], hint=_menu_hint())
        # Las operaciones largas, apartadas de las de diario.
        self.advanced_menu = Menu(
            self.aspect2d, menus.ADVANCED_TITLE, menus.ADVANCED_ITEMS,
            hint=_menu_hint(),
        )
        # Solo lectura: quién ha hecho los iconos, las tipografías y el resto.
        self.credits_menu = Menu(
            self.aspect2d, menus.CREDITS_TITLE, menus.build_credits_items(),
            hint=_menu_hint(),
        )
        # Los dos del modo desconocidos: título e items dinámicos.
        self.unknown_menu = Menu(self.aspect2d, "", [], hint=_menu_hint())
        self.unknown_results_menu = Menu(self.aspect2d, "", [], hint=_menu_hint())

        #: Todos los menús, para lo que haya que aplicarles a todos (de
        #: momento el color de acento). Añadir uno nuevo aquí y no en cada
        #: sitio que los recorra.
        self._menus = (
            self.options_menu, self.quit_menu, self.scoring_menu,
            self.scoring_config_menu, self.filter_menu, self.game_menu,
            self.settings_menu, self.accounts_menu, self.gui3d_menu,
            self.confirm_menu,
            self.unknown_menu, self.unknown_results_menu, self.advanced_menu,
            self.credits_menu,
        )

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
            # `hide`, no `close`: al volver hay que encontrarlo con el foco
            # donde estaba (ver `Menu.hide`).
            self.active_menu.hide()

        self._refresh_menu_accent()
        menu.open()
        self._menu_stack.append(menu)
        scoring_ui.show_scoring_description(self, menu is self.scoring_menu)
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
        # El sonido de "atrás" se engancha AQUÍ y no en `_on_back` ni en
        # `_on_escape_key`: los dos terminan llamando a este método, y
        # ponerlo arriba lo haría sonar dos veces.
        self.audio.play_back()

        # Salir de una confirmación con B no pasa por `_activate`, así que
        # el "qué hacer si dice que sí" se olvida aquí; si no, se quedaría
        # vivo reteniendo un juego que ya no interesa a nadie.
        if closed is self.confirm_menu:
            self._confirm_action = None

        # Si en el menú del juego se ha tocado "Oculto", el filtro se aplica
        # ahora, con el menú ya cerrado (ver `_on_game_flag_toggled`).
        if closed is self.game_menu and self._hidden_filter_dirty:
            self._hidden_filter_dirty = False
            self._apply_hidden_filter()
            self._on_selection_changed()

        if self.active_menu is not None:
            # `show`, no `open`: volver de un submenú tiene que devolverte a
            # la fila desde la que entraste, no a la primera.
            self.active_menu.show()
            # Al volver del formulario de configuración se vuelve a ver la
            # lista de sistemas, y con ella su descripción.
            scoring_ui.show_scoring_description(self, self.active_menu is self.scoring_menu)
        else:
            scoring_ui.show_scoring_description(self, False)
            # Se vació la pila: se vuelve al carrusel, así que la ficha
            # deshace la animación y reaparece.
            self._animate_ficha(visible=True)
            # Y se olvida con qué botón se había entrado. Si no, al salir
            # con B y abrir después otro menú distinto, el botón del menú
            # ANTERIOR seguiría cerrándolo (ver `_toggle_root_menu`).
            self._menu_opener = None
        self._reset_navigation()

    def _reset_navigation(self) -> None:
        self._nav_direction = 0
        self._nav_held_time = 0.0
        self._nav_next_repeat = 0.0
        # También el eje vertical: si no, al cerrar un cuadro de texto con
        # el stick a medio soltar quedaría un flanco pendiente y se
        # cambiaría de modo solo.
        self._mode_v_direction = 0

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
        entry = self.active_carousel.selected
        if entry is None:
            # Carrusel vacío (regenerando, o un filtro sin resultados): se
            # queda el acento que hubiera.
            return
        accent = as_text_color(primary_store_color(entry.stores))
        # Sobre `self._menus`, no sobre una lista escrita a mano: la de antes
        # se quedó sin actualizar al añadir el menú de configuración, y ese
        # salía con el amarillo por defecto en vez del color de la tienda.
        for menu in self._menus:
            menu.set_accent_color(accent)

    # ── Aperturas ──

    @property
    def _typing(self) -> bool:
        """
        ¿Se está escribiendo en el cuadro de texto?

        Los atajos de TECLADO se sueltan mientras tanto, pero los del MANDO
        siguen llegando (son eventos de dispositivo, no de teclado), así que
        todo lo que se pueda disparar con el mando tiene que consultarlo.
        """
        return self.text_prompt.is_open

    def _toggle_root_menu(self, menu: Menu, opener: str) -> None:
        """
        Abre `menu`, o cierra TODO si ya se entró con este mismo botón.

        Volver a pulsar el botón con el que se abrió devuelve a la pantalla
        principal de una vez, sin ir saliendo nivel a nivel: si has entrado
        en Opciones con Select y desde ahí en "Salir", Select te saca de los
        dos. Para retroceder un solo nivel está B (o Esc).

        Se compara con `_menu_opener` y no simplemente "hay un menú abierto"
        porque cada botón solo cierra LO SUYO: pulsar X dentro del menú de
        scoring no lo cierra, configura el sistema enfocado (ver
        `_on_filter_key`), que es lo que hace X ahí.

        El menú de juego se abre con A y queda fuera de esto a propósito: A
        dentro de un menú es "elegir", así que no puede significar también
        "cerrar" — marcaría la casilla y saldría en la misma pulsación.
        """
        if self._typing:
            return
        if self._menu_stack:
            if self._menu_opener == opener:
                self._close_all_menus()
            return

        self._menu_opener = opener
        self._push_menu(menu)

    def _open_options_menu(self) -> None:
        """Select / Esc sobre el carrusel."""
        if self._blocked_in_editor("Opciones"):
            return
        self._toggle_root_menu(self.options_menu, "options")

    def _open_scoring_menu(self) -> None:
        """Start / Tab sobre el carrusel."""
        if self._blocked_in_unknown_mode("Puntueitor"):
            return
        if self._blocked_in_editor("Puntueitor"):
            return
        self._toggle_root_menu(self.scoring_menu, "scoring")

    def _open_filter_menu(self) -> None:
        """X sobre el carrusel."""
        if not self._menu_stack:
            self.filter_menu.set_items(
                menus.build_filter_items(self.filters, TRISTATE_LABELS.get),
            )
        self._toggle_root_menu(self.filter_menu, "filter")

    def _on_filter_key(self) -> None:
        """
        La tecla "x" / botón X, que hace tres cosas según dónde estés: con el
        cuadro de texto abierto PEGA, dentro del menú de scoring configura el
        sistema enfocado, y en el resto de casos abre —o cierra— el menú de
        filtrar y ordenar.

        Que pegue desde aquí no es un apaño: el mando no pasa por el teclado,
        así que cada acción alcanzable con él comprueba `self._typing` y se
        va — o sea que X, mientras se escribe, no hacía nada. Se le da ese
        hueco en vez de buscar un botón libre, porque no queda ninguno y
        porque A y B ya funcionan igual, significando una cosa u otra según
        lo que haya en pantalla.
        """
        if self.text_prompt.is_open:
            self._paste_into_prompt()
            return
        if self._typing:
            return
        if self.active_menu is self.scoring_menu:
            scoring_ui.configure_focused_scoring(self)
        elif not self._blocked_in_unknown_mode("Filtrar"):
            if self._blocked_in_editor("Filtrar"):
                return
            self._open_filter_menu()

    def _open_game_menu(self) -> None:
        """A / Enter sobre el carrusel: las opciones del juego seleccionado."""
        entry = self.carousel.selected
        if entry is None:
            return
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
        # Un "abridor" que ningún botón puede igualar: el menú de juego se
        # abre con A, y A dentro de un menú significa "elegir", así que no
        # debe cerrarlo nadie por esta vía.
        self._menu_opener = "game"
        self._push_menu(self.game_menu)

    # ── Acciones ──

    def _on_confirm(self) -> None:
        """A / Enter: elige en el menú activo, o abre el del juego."""
        if self.text_prompt.is_open:
            # Con el cuadro abierto, A confirma lo escrito. (Enter no pasa
            # por aquí: los atajos están sueltos y lo recoge el propio
            # DirectEntry, que llama a su `command`.)
            self.text_prompt.accept_text()
            return

        menu = self.active_menu
        if menu is None:
            if self._unknown_mode:
                self._open_unknown_menu()
            elif not self._blocked_in_editor("Menú del juego"):
                self._open_game_menu()
            return

        item = menu.focused_item
        if item is None:
            return

        if item.kind == "check":
            menu.toggle_focused()
            # Las casillas salen en dos sitios y no significan lo mismo: en
            # el menú de juego marcan un estado del juego (y se guardan en la
            # base de datos), y en el de configuración, un género preferido.
            if menu is self.scoring_config_menu:
                scoring_ui.toggle_config_genre(self, item)
            elif menu is self.settings_menu:
                accounts_ui.toggle_setting_store(self, item)
            else:
                self._on_game_flag_toggled(item)
            return

        if item.kind == "cycle":
            # Estos se cambian con izquierda/derecha; A no hace nada sobre
            # ellos a propósito, para que no haya dos formas distintas de
            # tocar el mismo valor.
            return

        self._activate(menu, item.key)

    def _activate(self, menu: Menu, key: str) -> None:
        """Qué hace elegir un elemento de menú."""
        # Una sola llamada para las decenas de claves del despacho.
        self.audio.play_accept()
        if key == "accounts":
            accounts_ui.open_accounts_menu(self)
        elif key == "config":
            accounts_ui.open_settings_menu(self)
        elif key == "gui3d":
            accounts_ui.open_gui3d_menu(self)
        elif key == "advanced":
            self._push_menu(self.advanced_menu)
        elif key == "credits":
            self._push_menu(self.credits_menu)
        elif key == menus.CREDITS_BACK_KEY:
            self._pop_menu()
        elif key == menus.UPDATE_EXTRAS_KEY:
            self._confirm_update_extras()
        elif key == menus.ENRICH_ALL_KEY:
            self._confirm_enrich_all()
        elif key == menus.REGENERATE_KEY:
            self._confirm_regenerate()
        elif key == menus.BACKUP_KEY:
            backup_ui.ask_backup_path(self)
        elif key == menus.RESTORE_KEY:
            backup_ui.ask_restore_path(self)
        elif key == "quit":
            self._push_menu(self.quit_menu)
        elif key == "quit_yes":
            self.userExit()
        elif key == "quit_no":
            self._pop_menu()
        elif key.startswith("sort:"):
            self._apply_sort(key.removeprefix("sort:"))
        elif key == "filter:name":
            self._prompt_name_filter()
        elif key == "filter:duration":
            self._prompt_duration_filter()
        elif key == "filter:apply":
            self._apply_filters()
        elif key == "filter:clear":
            self._clear_filters()
        elif key.startswith("cfg:"):
            scoring_ui.activate_config(self, key)
        elif key == menus.UNKNOWN_TITLE_KEY:
            self._prompt_unknown_search()
        elif key == menus.UNKNOWN_STORE_KEY:
            self._resolve_by_store()
        elif key.startswith(menus.UNKNOWN_RESULT_PREFIX):
            self._adopt_selected_result(menu.focused_item)
        elif key == menus.ENRICH_KEY:
            self._confirm_enrich()
        elif key == menus.FORGET_KEY:
            self._confirm_forget()
        elif key == menus.CONFIRM_NO_KEY:
            self._confirm_action = None
            self._pop_menu()
        elif key == menus.CONFIRM_YES_KEY:
            self._run_confirmed_action()
        elif key == "set3d:save":
            accounts_ui.save_gui3d_settings(self)
        elif key.startswith(("set:", "login:")):
            # Las dos van a los menús de configuración: `set:` son los campos que
            # se editan y `login:` las filas de CUENTAS. Cuando esto solo
            # miraba `set:`, elegir una tienda no hacía nada visible — el
            # `else` de abajo se limitaba a apuntarlo en el log.
            accounts_ui.activate_setting(self, key)
        elif menu is self.scoring_menu:
            scoring_ui.apply_scorer(self, key)
        else:
            logger.info(f"gui3d: elegido {key!r} en el menú {menu.title!r}")

    # ── Filtros ──

    def _prompt_name_filter(self) -> None:
        self._open_text_prompt(
            title="Filtrar por nombre",
            initial=self.filters.name or "",
            on_accept=self._set_name_filter,
        )

    def _set_name_filter(self, text: str) -> None:
        self.filters.name = text or None
        self._refresh_filter_menu()

    def _prompt_duration_filter(self) -> None:
        current = self.filters.max_duration
        self._open_text_prompt(
            title="Duración máxima (horas)",
            initial=f"{current:g}" if current else "",
            on_accept=self._set_duration_filter,
        )

    def _set_duration_filter(self, text: str) -> None:
        # Un texto que no se entiende ("dos horas", "abc") deja el filtro
        # sin poner en vez de reventar; `parse_duration` ya devuelve None.
        self.filters.max_duration = parse_duration(text)
        self._refresh_filter_menu()

    def _refresh_filter_menu(self) -> None:
        """Vuelve a pintar los valores del menú de filtros sin mover el foco."""
        items = menus.build_filter_items(self.filters, TRISTATE_LABELS.get)
        by_key = {item.key: item for item in items}
        for item in self.filter_menu.items:
            nuevo = by_key.get(item.key)
            if nuevo is not None:
                item.value = nuevo.value
        self.filter_menu.refresh_values()

    def _adjust_focused(self, direction: int) -> None:
        """
        Izquierda/derecha sobre el elemento enfocado, sea cual sea el menú.

        Hoy hay dos clases de valor ajustables: los filtros de tres estados
        (N/A, Sí, No) y los números del formulario de scoring (pesos y
        horas). Se reparte aquí para que la detección de la pulsación viva
        en un solo sitio.
        """
        menu = self.active_menu
        if menu is None:
            return
        item = menu.focused_item
        if item is None or item.kind != "cycle":
            return

        if menu is self.filter_menu:
            field = item.payload.get("field")
            if field is None:
                return
            setattr(
                self.filters, field,
                cycle_tristate(getattr(self.filters, field), direction),
            )
            self._refresh_filter_menu()
        elif menu is self.scoring_config_menu:
            scoring_ui.adjust_config_value(self, item, direction)
        elif menu is self.gui3d_menu:
            accounts_ui.adjust_gui3d_setting(self, item, direction)

    def _focused_repeats(self) -> bool:
        """
        ¿El valor enfocado se puede mantener pulsado para ir cambiando?

        Los números sí (subir un peso de 40 a 60 son veinte toques), los
        filtros de tres estados no: con solo tres valores, un toque un poco
        largo daría la vuelta entera y se pasaría del que se busca.
        """
        menu = self.active_menu
        if menu is not self.scoring_config_menu:
            return False
        item = menu.focused_item
        return item is not None and item.kind == "cycle"

    def _apply_filters(self) -> None:
        """
        "Aplicar filtros": cierra el menú y rehace el carrusel.

        Un filtro que no deja NINGÚN juego se aplica igual y el carrusel se
        queda vacío. Antes no se aplicaba —el carrusel no sabía estar
        vacío—, y quedaba un estado que mentía: los filtros puestos y la
        biblioteca entera a la vista.
        """
        self._close_all_menus()
        self._apply_order(reset_selection=True)
        self._on_selection_changed()
        accounts_ui.persist_filters(self)
        if not self.carousel.visible_count:
            self.notifier.show("Ningún juego coincide")
        else:
            self.notifier.show(
                f"{self.carousel.visible_count} juegos"
                if self.filters.any_active else "Sin filtros"
            )

    def _clear_filters(self) -> None:
        self.filters.clear()
        self._close_all_menus()
        self._apply_order(reset_selection=True)
        self._on_selection_changed()
        accounts_ui.persist_filters(self)
        self.notifier.show("Filtros limpiados")

    def _apply_sort(self, sort_key: str) -> None:
        """
        Cambia la ordenación y deja el carrusel en el primer elemento.

        Se cierra el menú entero (no solo su nivel) porque elegir una
        ordenación es el final de esa tarea: dejarlo abierto obligaría a
        salir a mano para ver el resultado, que es justo lo que se acaba de
        pedir mirar.
        """
        criterion = sorting.CRITERIA.get(sort_key)
        if criterion is None:
            logger.warning(f"gui3d: ordenación desconocida {sort_key!r}")
            return

        self._sort_criterion = criterion
        self._close_all_menus()
        self._apply_order(reset_selection=True)
        self._on_selection_changed()
        # Con dos puntos y sin tocar la etiqueta: pasarla a minúsculas para
        # que encajara en la frase dejaba "SteamDB" como "steamdb".
        self.notifier.show(f"Ordenado por: {criterion.label}")
        logger.info(f"gui3d: ordenado por {sort_key!r}")

    def _close_all_menus(self) -> None:
        while self._menu_stack:
            self._pop_menu()
        self._menu_opener = None

    def _open_text_prompt(self, title: str, initial: str, on_accept) -> None:
        """
        Abre el cuadro de texto por encima del menú.

        El menú de debajo se APARTA mientras se escribe. El cuadro es más
        pequeño que un menú y se dibujaba encima, así que las filas del menú
        asomaban por los lados y por debajo y se leían las dos cosas a la
        vez. Al cerrar el cuadro vuelve con su foco intacto (`Menu.hide` /
        `Menu.show`), que es lo que permite seguir editando la misma fila.

        Se sueltan los atajos de teclado mientras está abierto: un
        `DirectEntry` con el foco no impide que Panda3D siga repartiendo las
        teclas, así que sin esto escribir "o" conmutaría los ocultos y "x"
        abriría otro menú encima (ver `_release_shortcuts`).
        """
        self._release_shortcuts()
        # Pegar se engancha AQUÍ y no en `self._shortcuts`, que es lo que
        # `_release_shortcuts` acaba de soltar entero: esto tiene que estar
        # activo justamente mientras el cuadro está abierto, que es al revés
        # que todo lo demás. Panda3D emite "control-v" porque `ShowBase`
        # registra Control como modificador del ButtonThrower.
        self.accept("control-v", self._paste_into_prompt)
        if self.active_menu is not None:
            self.active_menu.hide()
        self.text_prompt.open(
            title=title,
            hint=_prompt_hint(),
            initial=initial,
            on_accept=lambda text: self._close_text_prompt(on_accept, text),
            on_cancel=lambda: self._close_text_prompt(None, None),
        )

    def _close_text_prompt(self, on_accept, text) -> None:
        """
        Cierra el cuadro y devuelve los atajos... pero en el SIGUIENTE frame.

        Recuperarlos aquí mismo reabría el cuadro al instante al aceptar con
        Enter, y cuesta verlo: al pulsar Enter se encolan DOS eventos en la
        misma tanda. Primero el `accept` del `DirectEntry` (que trae aquí), y
        justo detrás el evento de tecla "enter" que lanza el ButtonThrower,
        que no desaparece por tener el foco puesto en el cuadro. Si en el
        primero se vuelven a coger los atajos, el segundo ya encuentra
        escuchando a `_on_confirm`, que como el foco del menú sigue en
        "Nombre" vuelve a abrir el cuadro. El filtro SÍ se aplicaba; lo que
        parecía es que Enter no hacía nada.

        Con un frame de margen, ese "enter" rezagado no lo escucha nadie.
        Esc no se ve afectado porque nunca se llega a soltar.
        """
        self.ignore("control-v")
        self.task_mgr.remove(_REBIND_TASK)
        self.task_mgr.do_method_later(
            0, self._rebind_shortcuts_task, _REBIND_TASK,
        )
        # El menú vuelve ANTES de aplicar el valor: quien lo aplique va a
        # repintar sus filas, y para eso tiene que estar ya en pantalla.
        if self.active_menu is not None:
            self.active_menu.show()
        if on_accept is not None:
            on_accept(text)

    def _paste_into_prompt(self) -> None:
        """
        Pega el portapapeles en el cuadro (Ctrl-V, o el botón X del mando).

        Existe por el login de las tiendas: se vuelve del navegador con una
        URL de cuatrocientos caracteres en el portapapeles, y sin esto había
        que teclearla — con un mando, si estás en el sofá.
        """
        if not self.text_prompt.is_open:
            return

        from puntueitor.core.services.clipboard import read_clipboard

        texto, motivo = read_clipboard()
        if motivo:
            self.notifier.show(motivo)
            return

        pegados = self.text_prompt.paste(texto)
        if pegados:
            self.notifier.show(f"Pegados {pegados} caracteres")
        else:
            # Pasa si el portapapeles solo traía saltos de línea, que el
            # cuadro no admite. Decirlo evita quedarse mirando la pantalla.
            self.notifier.show("No había nada que pegar")

    def _rebind_shortcuts_task(self, task):
        self._bind_shortcuts()
        return task.done

    def _jump_start(self) -> None:
        """
        L3 (o la tecla Inicio): al principio del carrusel.

        Sobre `active_carousel` y no sobre `self.carousel`, así que vale
        también en el modo desconocidos: allí quiere decir lo mismo y no hay
        motivo para bloquearlo, al revés que `_jump_group`, que va por grupos
        de la ordenación y en desconocidos no hay.

        Sin aviso: el salto se ve solo. `_jump_group` sí avisa, pero porque la
        etiqueta del grupo al que llega no está en ninguna otra parte.
        """
        if self._typing or self.active_menu is not None:
            return
        if not self.active_carousel.jump_to_start():
            return
        self._on_selection_changed()

    def _jump_group(self, direction: int) -> None:
        """
        L1/R1 (teclas "q" y "w"): salto rápido al grupo anterior/siguiente
        de la ordenación actual — la inicial siguiente, o el tramo de cinco
        puntos u horas siguiente.

        No hace nada con un menú abierto: ahí las mismas teclas no pintan
        nada y mover el carrusel por detrás solo desconcierta.
        """
        if (
            self._typing
            or self.active_menu is not None
            or self._blocked_in_unknown_mode("Saltar")
        ):
            return
        if not self.carousel.jump_to_group(direction):
            return

        self._on_selection_changed()
        criterion = self._sort_criterion
        group = self.carousel.group_at_selection(self._groups)
        self.notifier.show(sorting.group_label(criterion, group))

    # ── Ajustes del frontend 3D ──

    # ── Menú de juego ──

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

        El detalle de qué se escribe y dónde está en `_persist_flags`, que
        comparte con el Editor Rápido: son la misma operación por dos caminos
        distintos, y duplicarla es como se acaba poniendo tres estados a
        False sin querer.
        """
        entry = self._game_menu_entry
        game = entry.game if entry else None
        field = item.payload.get("field")
        if game is None or field is None:
            return

        setattr(game, field, item.checked)
        self._persist_flags(game)
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

    # ── Acciones avanzadas del menú de juego ──

    def _ask_confirm(
        self, title, question_lines, yes_label, on_yes, warning: int = 0,
    ) -> None:
        """
        Abre una pregunta de sí/no encima del menú actual.

        Se recuerda QUÉ hacer, no sobre qué: cada acción se guarda ya atada a
        su juego (con un `lambda`), así que la confirmación no tiene que
        saber nada de lo que va a ejecutar y sirve igual para lo siguiente
        que haga falta preguntar.
        """
        self._confirm_action = on_yes
        self.confirm_menu.set_title(title)
        self.confirm_menu.set_items(
            menus.build_confirm_items(question_lines, yes_label, warning=warning)
        )
        self._push_menu(self.confirm_menu)

    def _run_confirmed_action(self) -> None:
        """Se ha dicho que sí: cerrar los menús y ejecutar lo pendiente."""
        action = self._confirm_action
        # Se olvida ANTES de ejecutar, no después: es lo que impide que una
        # segunda pulsación repita la acción.
        self._confirm_action = None
        # Y se cierra todo antes de actuar: las dos acciones avisan por el
        # notificador y cambian el carrusel, y dejar menús abiertos encima
        # taparía justo el resultado que se acaba de pedir ver.
        self._close_all_menus()
        if action is not None:
            action()

    def _confirm_enrich(self) -> None:
        entry = self._game_menu_entry
        if entry is None or entry.game is None:
            return
        self._ask_confirm(
            entry.title, menus.ENRICH_QUESTION, menus.ENRICH_YES,
            lambda e=entry: self._start_enrich(e),
        )

    def _start_enrich(self, entry) -> None:
        """Encola el enriquecido de un juego y avisa de que ha empezado."""
        if not self.enrich_worker.request(entry.key, entry.game):
            self.notifier.show(f"Ya se está enriqueciendo {entry.title}")
            return
        self.notifier.show(f"Enriqueciendo {entry.title}...")

    def _on_enrich_done(self, key, result) -> None:
        """
        Aplica lo que ha traído el hilo de enriquecido, en el hilo principal.

        La entrada se busca por `key` en vez de guardarse desde el principio:
        entre que se pidió y llegó el resultado el juego puede haber
        desaparecido del carrusel (desconocido, sin ir más lejos).
        """
        entry = next((e for e in self.entries if e.key == key), None)
        if entry is None or entry.game is None:
            return

        if not result.ok:
            self.notifier.show(f"No se pudo enriquecer: {describe_error(result.error)}")
            return
        if not result.found:
            self.notifier.show(f"Sin datos para {entry.title}")
            return

        # Los datos se copian ENCIMA del juego que ya está en la entrada, en
        # vez de sustituir la entrada por otra con el juego nuevo:
        # `CarouselEntry` es inmutable y el carrusel guarda sus propias
        # referencias, así que cambiarla dejaría a `carousel.selected.game`
        # y a `self.entries` enseñando datos distintos. `Game` sí es mutable
        # y es lo que ya hace `_on_game_flag_toggled` con las casillas.
        for field in EXTRA_FIELDS:
            setattr(entry.game, field, getattr(result.game, field))

        # La caja enseña la nota y la duración, así que hay que repintarla.
        self.carousel.rebuild_labels(entry.key, entry.game, self._labels_visible)
        seleccionado = self.carousel.selected
        if seleccionado is not None and seleccionado.key == key:
            self._refresh_selection_text()
        self.notifier.show(f"Enriquecido: {entry.title}")

    def _forget_game(self, entry) -> None:
        """
        Saca el juego de la biblioteca y del carrusel.

        No se destruye su caja: basta con dejar de listarlo, porque
        `Carousel.set_order` esconde todo lo que no esté en el orden. Y sin
        `reset_selection` la selección se queda en el juego siguiente al que
        acaba de irse, en vez de saltar al principio de la biblioteca.

        Si era el último, el carrusel se queda vacío y no pasa nada: es un
        estado que sabe dibujar.
        """
        forget_game(self.library_repository, entry.game)
        self.entries = [e for e in self.entries if e.key != entry.key]
        # Acaba de aparecer en `unknown_games`: el carrusel de desconocidos
        # que hubiera construido ya no coincide con lo que hay en disco.
        self._invalidate_unknown_carousel()

        self._apply_order()
        self._on_selection_changed()
        self.notifier.show(f"Desconocido: {entry.title}")

    def _confirm_forget(self) -> None:
        entry = self._game_menu_entry
        if entry is None or entry.game is None:
            return
        self._ask_confirm(
            entry.title, menus.FORGET_QUESTION, menus.FORGET_YES,
            lambda e=entry: self._forget_game(e),
        )

    # ──────────────────────────────
    # Actualizar la biblioteca (R2 / tecla "r")
    # ──────────────────────────────

    def _refresh_library(self) -> None:
        """
        Vuelve a preguntar a las tiendas y añade lo que no estuviera.

        Es la variante "suave" de la TUI (su tecla "r"): **no borra nada**.
        Los juegos ya resueltos no se vuelven a consultar en IGDB, así que lo
        que de verdad cuesta es la vuelta a la API de Steam y resolver lo
        nuevo.

        No se pide confirmación: no destruye nada y se puede seguir navegando
        mientras trabaja. Las dos que sí destruyen están en Opciones ->
        Avanzado, y esas preguntan.
        """
        if self._typing or self._blocked_in_unknown_mode("Actualizar"):
            return
        if self._blocked_in_editor("Actualizar"):
            return
        self._start_library_job(SOFT)

    def _build_carousel(self, raw_entries, pending_downloads) -> None:
        """
        Monta el carrusel de la biblioteca a partir de lo leído del disco.

        Lo usan el arranque y la reconstrucción de después de regenerar, para
        que no puedan divergir: si un día se añade algo al montaje, el
        carrusel rehecho lo tendrá también.
        """
        self.entries = [
            CarouselEntry(
                key=e["key"], title=e["title"], texture=e["texture"],
                stores=e.get("stores", frozenset()), game=e.get("game"),
            )
            for e in raw_entries
        ]
        self.carousel_root = self.render.attach_new_node("carousel-root")
        self.carousel_root.set_z(CAROUSEL_RAISE)
        self.carousel = Carousel(
            self.carousel_root, self.entries,
            score_source=self.prefs.score_source,
        )
        # Carátulas que aún no están en disco: se piden a medida que se
        # navega (ver `_request_nearby_covers`), nunca todas de golpe.
        self._pending_covers = {
            key: (igdb_id, cover_url) for key, igdb_id, cover_url in pending_downloads
        }

    def _clear_carousel(self) -> None:
        """
        Deja el carrusel sin ninguna caja.

        Es un estado normal, no una avería: mientras se regenera la
        biblioteca no hay nada que enseñar, y el carrusel lo sabe dibujar
        (ver `Carousel.clear` y `Carousel.selected`, que devuelve None).
        """
        self.entries = []
        self._pending_covers.clear()
        self.carousel.clear()
        self._on_selection_changed()
        logger.info("gui3d: carrusel vaciado")

    # ── Copia de seguridad ──

    def _confirm_update_extras(self) -> None:
        """
        Opciones -> Avanzado -> Enriquecer todo.

        `warning=0`: no hay ninguna línea que pintar en rojo porque no se
        pierde nada, solo se reescribe encima.
        """
        self._ask_confirm(
            menus.UPDATE_EXTRAS_TITLE,
            menus.UPDATE_EXTRAS_NOTE,
            menus.UPDATE_EXTRAS_YES,
            lambda: self._start_library_job(UPDATE_EXTRAS),
        )

    def _confirm_enrich_all(self) -> None:
        """Opciones -> Avanzado -> Enriquecer todo DESTRUCTIVO (la "E" de la TUI)."""
        self._ask_confirm(
            menus.ENRICH_ALL_TITLE,
            menus.ENRICH_ALL_WARNING + menus.ENRICH_ALL_NOTE,
            menus.ENRICH_ALL_YES,
            lambda: self._start_library_job(ENRICH_ALL),
            warning=len(menus.ENRICH_ALL_WARNING),
        )

    def _confirm_regenerate(self) -> None:
        """Opciones -> Avanzado -> Regenerar todo (la "R" de la TUI)."""
        self._ask_confirm(
            menus.REGENERATE_TITLE,
            menus.REGENERATE_WARNING + menus.REGENERATE_NOTE,
            menus.REGENERATE_YES,
            lambda: self._start_library_job(REGENERATE),
            warning=len(menus.REGENERATE_WARNING),
        )

    def _start_library_job(self, mode: str) -> None:
        """Arranca uno de los tres trabajos y enciende el contador."""
        if not self.refresh_worker.start(mode):
            self.notifier.show("Ya hay un proceso en curso")
            return

        self._refresh_added = 0
        etiqueta = MODE_LABELS[mode]
        self.refresh_text.setText(f"{etiqueta}…")
        self.refresh_text.show()
        self.notifier.show(f"{etiqueta}...")

        if mode == REGENERATE:
            # El carrusel se vacía YA, no al terminar: la base se está
            # borrando entera, así que seguir enseñando la biblioteca de
            # antes durante los minutos que dura sería enseñar algo que ya
            # no existe. Los juegos van reapareciendo según se resuelven.
            self._clear_carousel()
            # Y `unknown_games` estaba en esa misma base.
            self._invalidate_unknown_carousel()

        logger.info(f"gui3d: {etiqueta.lower()}")

    def _drain_refresh(self) -> None:
        """
        Recoge lo que va mandando la actualización, una vez por frame.

        Las cajas nuevas se acumulan y se ordenan UNA sola vez al final del
        frame aunque hayan llegado varias: `_apply_order` recoloca las 1266
        cajas, y hacerlo por juego daría un tirón por cada uno.
        """
        nuevas = False
        for kind, payload in self.refresh_worker.poll():
            if kind == PROGRESS:
                self._show_refresh_progress(payload)
            elif kind == GAME:
                nuevas |= self._on_game_refreshed(payload)
            elif kind == DONE:
                self._on_refresh_done(payload)

        if nuevas:
            # Sin `reset_selection`: al contrario que la TUI, que salta al
            # primero al recargar, aquí te quedas en el juego que estabas
            # mirando.
            self._apply_order()
            self._on_selection_changed()

    def _show_refresh_progress(self, progress) -> None:
        self.refresh_text.setText(
            f"Actualizando…\n{progress.name}\n"
            f"{progress.current} / {progress.total}"
        )

    def _on_game_refreshed(self, game) -> bool:
        """
        Un juego que ha traído la actualización. True si es uno nuevo.

        Llegan los de siempre también (el pipeline los emite todos, y los
        enriquecidos vuelven a pasar por aquí), así que lo primero es mirar
        si ya tiene caja. Si la tiene, se aprovecha para repintar sus
        etiquetas: puede venir con la duración o la nota recién averiguadas.
        """
        if self._sample_mode:
            # Llega el primero de verdad: fuera los de mentira. Aquí y no al
            # empezar la recarga, porque si la recarga no trae nada —sin
            # credenciales, sin red— es mejor quedarse con los ejemplos que
            # con una pantalla vacía; y aquí ya hay algo real con lo que
            # sustituirlos.
            #
            # Y ANTES de buscar duplicados, no después: los ejemplos usan
            # `igdb_id` 0-5, que IGDB también usa de verdad, así que un juego
            # real con uno de esos ids se tomaría por una entrada de ejemplo y
            # se le pisarían los datos en vez de darle su caja.
            self._sample_mode = False
            self._clear_carousel()
            logger.info(
                "gui3d: fuera los juegos de ejemplo, llega la biblioteca de verdad"
            )

        existente = next(
            (entry for entry in self.entries if entry.key == game.igdb_id), None,
        )
        if existente is None and not game.cover_url:
            # El mismo criterio que `real_data.build_real_entries`, que es
            # quien decide qué se puede enseñar: sin carátula no hay caja.
            # Sin esto entraban juegos —DLCs, sobre todo— que desaparecían
            # al reiniciar, porque el arranque sí los descarta.
            return False
        if existente is not None:
            if existente.game is not None:
                for field in EXTRA_FIELDS:
                    setattr(existente.game, field, getattr(game, field))
                self.carousel.rebuild_labels(
                    existente.key, existente.game, self._labels_visible,
                )
            return False

        self._add_game_entry(game)
        self._refresh_added += 1
        logger.info(f"gui3d: juego nuevo en la biblioteca: {game.title!r}")
        return True

    def _on_refresh_done(self, done) -> None:
        self.refresh_text.hide()
        if not done.ok:
            self.notifier.show(f"No se pudo actualizar: {describe_error(done.error)}")
            return
        # Los juegos AÑADIDOS, no lo que emitió el pipeline: un juego que
        # está en dos tiendas se emite dos veces, así que ese número no es el
        # tamaño de tu biblioteca y desconcierta más que informa.
        if self.refresh_worker.mode == REGENERATE:
            # No hay nada que rehacer: se vació al empezar y las cajas han
            # ido entrando según se resolvían, así que el carrusel ya es
            # exactamente lo que hay en la base.
            self.notifier.show(f"Biblioteca regenerada ({len(self.entries)} juegos)")
        elif self._refresh_added:
            self.notifier.show(f"{self._refresh_added} juegos nuevos")
        else:
            self.notifier.show("Biblioteca al día")
        logger.info(
            f"gui3d: terminado ({done.loaded} juegos recorridos, "
            f"{self._refresh_added} nuevos)"
        )

    # ──────────────────────────────
    # Modo desconocidos
    # ──────────────────────────────

    @property
    def active_carousel(self):
        """
        El carrusel que se está viendo.

        Casi todo lo que dice `self.carousel` quiere decir en realidad
        "el de delante". Las excepciones son las carátulas
        (`_request_nearby_covers`, `_on_cover_ready`, `_backfill_covers`) y
        todo lo que ordena o filtra: esas cosas son de la biblioteca y
        siguen apuntando al principal aunque estés en desconocidos.
        """
        return self._unknown_carousel if self._unknown_mode else self.carousel

    def _build_unknown_carousel(self) -> bool:
        """
        Construye el carrusel de desconocidos. False si no hay ninguno.

        Perezoso: son unas decenas de cajas más y un hilo, y la mayoría de
        las sesiones no entran aquí. Con la biblioteca real son 48 cajas,
        unos 50 ms de tirón la primera vez que se pulsa arriba.
        """
        unknowns = unknown_actions.list_unknowns(self.library_repository)
        if not unknowns:
            # `Carousel` no sabe existir vacío (ver su constructor), y
            # tampoco habría nada que enseñar.
            self.notifier.show("No hay juegos desconocidos")
            return False

        # Una sola textura para todas: `make_placeholder_texture` cachea por
        # color, así que las 48 cajas comparten la misma de 2x2.
        texture = make_placeholder_texture(UNKNOWN_COVER_COLOR)
        self._unknown_entries = [
            CarouselEntry(
                key=unknown.key,
                title=unknown.title,
                texture=texture,
                stores=_store_set(unknown.store),
                game=None,
            )
            for unknown in unknowns
        ]

        self._unknown_root = self.render.attach_new_node("unknown-carousel-root")
        self._unknown_root.set_z(CAROUSEL_RAISE)
        self._unknown_root.hide()
        self._unknown_carousel = Carousel(
            self._unknown_root, self._unknown_entries,
            body_color=UNKNOWN_BODY_COLOR, cover_caption=True,
        )
        if self.unknown_worker is None:
            self.unknown_worker = UnknownWorker(self.library_repository)
        logger.info(f"gui3d: {len(self._unknown_entries)} juegos desconocidos")
        return True

    def _invalidate_unknown_carousel(self) -> None:
        """
        Tira el carrusel de desconocidos para que se rehaga con la lista de
        verdad la próxima vez.

        Se usa cuando la tabla ha cambiado por detrás (al desconocer un
        juego de la biblioteca): rehacer 48 cajas cuesta 50 ms y solo pasa
        tras esa acción, mientras que mantenerlo sincronizado a mano sería
        una fuente de listas que no coinciden con lo que hay en disco.
        """
        if self._unknown_root is not None:
            self._unknown_root.remove_node()
        self._unknown_root = None
        self._unknown_carousel = None
        self._unknown_entries = []

    def _enter_unknown_mode(self) -> None:
        if self._unknown_carousel is None and not self._build_unknown_carousel():
            return
        self._unknown_mode = True
        self.carousel_root.hide()
        self._unknown_root.show()
        self.ficha_frame.hide()
        self.unknown_frame.show()
        self._on_selection_changed()
        self.notifier.show(f"{len(self._unknown_entries)} juegos desconocidos")

    def _exit_unknown_mode(self) -> None:
        if not self._unknown_mode:
            return
        self._unknown_mode = False
        if self._unknown_root is not None:
            self._unknown_root.hide()
        self.carousel_root.show()
        self.unknown_frame.hide()
        self.ficha_frame.show()
        self._on_selection_changed()

    def _vertical_direction(self) -> int:
        """
        Arriba/abajo SOBRE EL CARRUSEL, de teclado o de mando.

        Devuelve 0 con un menú abierto o escribiendo: allí el eje vertical
        es la navegación del menú (la lee `_held_direction`), y si no,
        subir por una lista de opciones cambiaría de modo por detrás.
        """
        if self._typing or self.active_menu is not None:
            return 0
        direction = (
            (1 if self._keys_held["down"] else 0)
            - (1 if self._keys_held["up"] else 0)
        )
        if direction:
            return direction
        return self.gamepad.direction_v() if self.gamepad else 0

    def _update_mode_switch(self, dt: float) -> None:
        """
        Entra y sale del modo desconocidos con arriba y abajo.

        Solo en el FLANCO y sin repetición: cambiar de modo no es recorrer
        una lista, y dejar arriba pulsado no debe hacer nada más que entrar
        una vez.

        Se sondea el estado (como `_update_menu_cycle`) en vez de escuchar
        el evento de tecla para que el teclado y el mando sigan el mismo
        camino: el stick no emite eventos, solo se puede leer su posición.
        """
        direction = self._vertical_direction()
        if direction == self._mode_v_direction:
            return
        self._mode_v_direction = direction

        if direction and self._blocked_in_editor("Desconocidos"):
            # Con el editor activo, arriba y abajo no cambian de modo: los
            # desconocidos no tienen estados que editar, y entrar ahí sin
            # querer con el stick en la mano dejaría el editor activo sobre
            # un carrusel que no lo entiende.
            return

        if direction < 0:
            if not self._unknown_mode:
                self._enter_unknown_mode()
        elif direction > 0:
            self._exit_unknown_mode()

    # ── Guardas compartidas (Editor Rápido, menú de juego) ──

    def _blocked_in_editor(self, gesture: str = "") -> bool:
        """
        Los gestos que el Editor Rápido se come, y por qué se avisa.

        Hermana de `_blocked_in_unknown_mode`: en este modo el stick derecho
        escribe en la base de datos, así que abrir menús por encima es pedir
        equivocarse de juego. Se avisa en vez de ignorar en silencio, y el
        aviso dice CÓMO salir.
        """
        if not self._editor_mode:
            return False
        if gesture:
            self.notifier.show(menus.EDITOR_BLOCKED.format(gesto=gesture))
        return True

    def _persist_flags(self, game) -> None:
        """
        Escribe los cuatro estados del juego en `library.sqlite`.

        LOS CUATRO, no solo el que se acaba de tocar: `set_status` reescribe
        la fila entera (es un UPSERT), así que pasarle uno solo pondría los
        otros tres a False.

        Van a `library_cacher` y NO a `save_game()` del repositorio, que fue
        el primer intento y no guardaba nada: ese solo persiste los extras
        (duración, notas de Steam) y los estados del usuario viven en OTRA
        base de datos a propósito — la de extras es caché regenerable y esta
        no, para que borrar la caché no te borre los terminados.

        Y por eso mismo los juegos de ejemplo no escriben: sus `igdb_id` son
        0-5, así que dejarían filas que no corresponden a ningún juego tuyo
        en la ÚNICA base que no se puede regenerar. No estorbarían al pintar
        —`load()` solo aplica estados a ids que estén en `resolvers`— pero se
        quedarían ahí para siempre.
        """
        if self._sample_mode:
            self.notifier.show("Son juegos de ejemplo: no se guarda nada")
            return

        self.library_repository.library_cacher.set_status(
            game.igdb_id,
            finished=game.finished,
            hidden=game.hidden,
            backlog=game.backlog,
            favorite=game.favorite,
        )

    def _blocked_in_unknown_mode(self, gesture: str = "") -> bool:
        """
        Los gestos que no significan nada sobre un desconocido: no tiene
        estados, ni nota, ni entra en los filtros ni en el orden.

        Se avisa en vez de ignorar en silencio: pulsar y que no pase nada
        parece que la aplicación se ha colgado.
        """
        if not self._unknown_mode:
            return False
        if gesture:
            self.notifier.show(f"{gesture}: solo en la biblioteca")
        return True

    def _refresh_unknown_text(self) -> None:
        """El título arriba y, abajo, de dónde sale y por dónde vas."""
        carousel = self._unknown_carousel
        if carousel is None:
            return
        entry = carousel.selected
        if entry is None:
            return
        store, store_id = entry.key
        self.title_text.setText(entry.title)
        self.unknown_value_texts[0].setText(store)
        self.unknown_value_texts[1].setText(store_id)
        self.unknown_count_text.setText(
            f"{carousel.selected_position + 1} de {carousel.visible_count}"
        )

    def _open_unknown_menu(self) -> None:
        """A sobre un desconocido: las dos formas de identificarlo."""
        carousel = self._unknown_carousel
        if carousel is None:
            return
        entry = carousel.selected
        if entry is None:
            return
        self.unknown_menu.set_title(entry.title)
        self.unknown_menu.set_items(menus.build_unknown_items(entry))
        self._unknown_menu_entry = entry
        self._push_menu(self.unknown_menu)

    def _selected_unknown(self):
        """El `Unknown` sobre el que se abrió el menú, o None."""
        entry = getattr(self, "_unknown_menu_entry", None)
        if entry is None:
            return None
        store, store_id = entry.key
        return unknown_actions.Unknown(store=store, title=entry.title, id=store_id)

    def _prompt_unknown_search(self) -> None:
        """
        Pide el texto a buscar, con el título del juego ya escrito.

        Prellenado y no en blanco porque casi siempre el título es correcto
        y lo que falla es un subtítulo o una edición: se corrige lo que
        sobra en vez de teclearlo entero con un mando.
        """
        unknown = self._selected_unknown()
        if unknown is None:
            return
        self._open_text_prompt(
            "Buscar en IGDB", unknown.title,
            lambda text, u=unknown: self._start_unknown_job(
                UnknownJob(kind=SEARCH, unknown=u, query=text),
                f"Buscando {text}...",
            ),
        )

    def _start_unknown_job(self, job, message: str) -> None:
        """
        Encola una gestión lenta y cierra los menús.

        Se cierran porque tarda segundos y el menú se quedaría ahí quieto
        sin decir nada, que se lee como un cuelgue; el aviso del notificador
        sí dice qué está pasando.
        """
        if not job.query and job.kind == SEARCH:
            return
        if self.unknown_worker is None or not self.unknown_worker.request(job):
            self.notifier.show(f"Ya se está buscando {job.unknown.title}")
            return
        self._close_all_menus()
        self.notifier.show(message)

    def _on_unknown_job_done(self, job, result) -> None:
        """Recoge en el hilo principal lo que ha traído el de trabajo."""
        if job.kind == SEARCH:
            self._on_search_done(job, *result)
        else:
            self._on_adopt_done(result)

    def _on_search_done(self, job, results, error) -> None:
        if error is not None:
            self.notifier.show(f"No se pudo buscar: {describe_error(error, 'IGDB')}")
            return
        if not results:
            self.notifier.show("Sin resultados en IGDB")
            return
        if not self._unknown_mode:
            # Se ha vuelto a la biblioteca mientras se buscaba; abrir aquí
            # un menú de resultados sería aparecerse encima de otra cosa.
            self.notifier.show("Búsqueda cancelada")
            return

        # El menú se abre para el desconocido sobre el que se PIDIÓ, aunque
        # el usuario haya navegado a otro mientras tanto: es su búsqueda, y
        # descartarla por haber movido el stick sería perder los segundos de
        # espera. Mismo criterio que `_game_menu_entry`.
        self._unknown_search_target = job.unknown
        self.unknown_results_menu.set_title(job.unknown.title)
        self.unknown_results_menu.set_items(menus.build_search_result_items(results))
        self._push_menu(self.unknown_results_menu)

    def _adopt_selected_result(self, item) -> None:
        unknown = getattr(self, "_unknown_search_target", None)
        result = item.payload.get("result")
        if unknown is None or result is None:
            return
        self._start_unknown_job(
            UnknownJob(kind=ADOPT, unknown=unknown, result=result),
            f"Añadiendo {result.title}...",
        )

    def _resolve_by_store(self) -> None:
        unknown = self._selected_unknown()
        if unknown is None:
            return
        self._start_unknown_job(
            UnknownJob(kind=STORE, unknown=unknown),
            f"Buscando {unknown.title} en {unknown.store}...",
        )

    def _on_adopt_done(self, result) -> None:
        """Ha terminado un intento de identificar: se avisa y, si salió, se
        mete el juego en el carrusel de la biblioteca."""
        if result.unsupported:
            self.notifier.show(f"{result.unknown.store}: hay que buscarlo por título")
            return
        if result.error is not None:
            self.notifier.show(f"Error: {result.error}")
            return
        if result.game is None:
            # `unknown_actions` ya lo ha devuelto a la tabla.
            self.notifier.show(f"Sin resultados para {result.unknown.title}")
            return

        self._add_adopted_game(result.game)
        self._remove_unknown_entry(result.unknown)
        self.notifier.show(f"Añadido: {result.game.title}")

    def _add_adopted_game(self, game) -> None:
        """
        Mete en el carrusel el juego recién identificado, sin reiniciar.

        La caja se construye ahora (una sola, ~1 ms) y entra en el recorrido
        por `_apply_order`, con el filtro y la ordenación que haya puestos —
        así que si hay un filtro activo que no cumple, no se verá hasta
        quitarlo, igual que cualquier otro juego.
        """
        self._add_game_entry(game)
        self._apply_order()

    def _add_game_entry(self, game) -> None:
        """
        Le hace su caja a un juego que no estaba y la mete en el carrusel.

        NO reordena: quien llama decide cuándo, porque al actualizar la
        biblioteca pueden llegar varios juegos en el mismo frame y
        `_apply_order` recoloca las 1266 cajas de una vez.
        """
        stores = frozenset(game.stores)
        texture = load_cover_texture(game.igdb_id, game.cover_url, allow_download=False)
        if texture is None:
            texture = make_placeholder_texture(primary_store_color(stores))
            if game.cover_url:
                # Que la pida `_request_nearby_covers` cuando toque, igual
                # que las de cualquier otro juego sin carátula en disco.
                self._pending_covers[game.igdb_id] = (game.igdb_id, game.cover_url)

        entry = CarouselEntry(
            key=game.igdb_id, title=game.title, texture=texture,
            stores=stores, game=game,
        )
        self.entries.append(entry)
        self.carousel.add_entry(entry)

    def _remove_unknown_entry(self, unknown) -> None:
        """Saca de los desconocidos al que se acaba de identificar."""
        if self._unknown_carousel is None:
            return
        self._unknown_entries = [
            entry for entry in self._unknown_entries if entry.key != unknown.key
        ]
        if not self._unknown_entries:
            # Era el último: el carrusel no sabe quedarse vacío, así que se
            # sale del modo y se desmonta entero.
            self._exit_unknown_mode()
            self._invalidate_unknown_carousel()
            self.notifier.show("No quedan juegos desconocidos")
            return

        self._unknown_carousel.remove_entry(unknown.key)
        if self._unknown_mode:
            self._refresh_unknown_text()

    def _on_back(self) -> None:
        """
        El botón B: vuelve al menú anterior.

        Sobre el carrusel no hace nada a propósito — es "volver", y en la
        pantalla principal no hay a dónde volver. Quien abre Opciones ahí es
        Select (o Esc en el teclado, ver `_on_escape_key`).
        """
        if self.text_prompt.is_open:
            self.text_prompt.cancel()
            return
        if self._menu_stack:
            self._pop_menu()
        elif self._unknown_mode:
            # Aquí sí hay a dónde volver: a la biblioteca. Es lo mismo que
            # hace abajo, y "volver" es justo lo que se espera de B.
            self._exit_unknown_mode()

    def _on_escape_key(self) -> None:
        """
        La tecla Esc hace de B y de Select a la vez, porque el teclado no
        tiene un equivalente cómodo a los dos: dentro de un menú vuelve, y
        en la pantalla principal abre Opciones.
        """
        if self.text_prompt.is_open:
            self.text_prompt.cancel()
            return
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
        if not self._unknown_mode:
            # Los desconocidos no tienen carátula que pedir: no están en
            # IGDB, que es de donde salen.
            self._request_nearby_covers()
        self._refresh_menu_accent()

    def _update_background(self, dt: float) -> None:
        """Pone de fondo la carátula seleccionada, si lleva un rato quieta."""
        self._settle_time += dt
        if self._settle_time < BACKGROUND_SETTLE_DELAY:
            return

        entry = self.active_carousel.selected
        if entry is None:
            # Sin selección se deja el fondo que hubiera: no hay carátula de
            # la que sacar uno nuevo.
            return
        key = entry.key
        texture = self.active_carousel.selected_texture
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
        if self._unknown_mode:
            self._refresh_unknown_text()
            return

        entry = self.carousel.selected
        if entry is None:
            # Con el carrusel vacío el HUD se queda en blanco: no hay juego
            # del que hablar, y dejar el anterior sería mentir.
            self.title_text.setText("")
            for value_text in self.ficha_value_texts:
                value_text.setText("")
            self.description_text.setText("")
            return

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
        self._update_menu_cycle(dt)
        self._update_mode_switch(dt)
        editor_ui.update_editor(self)
        self.active_carousel.update(dt)

        for key, path in self.cover_loader.poll():
            self._on_cover_ready(key, path)

        for key, result in self.enrich_worker.poll():
            self._on_enrich_done(key, result)

        if self.unknown_worker is not None:
            for job, result in self.unknown_worker.poll():
                self._on_unknown_job_done(job, result)

        self._drain_refresh()

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
        self.enrich_worker.shutdown()
        self.refresh_worker.shutdown()
        if self.unknown_worker is not None:
            self.unknown_worker.shutdown()
        self.gamepad.destroy()
        super().destroy()


def main() -> None:
    # Lo PRIMERO, antes de que nada abra una base de datos: si un cacher
    # creara antes el fichero destino, la migración lo vería ocupado y
    # dejaría los datos del usuario huérfanos en la ruta antigua. Ver
    # `paths.migrate_legacy_paths`.
    paths.migrate_legacy_paths()

    # Y justo después, porque escribe el log en su sitio definitivo. Hasta
    # ahora el carrusel solo hacía un `basicConfig` a stderr al importarse:
    # lanzado desde Steam, que es como se usa, no quedaba ni una línea en
    # ninguna parte. `console=True` mantiene además la salida por terminal de
    # siempre para quien lo abra desde una.
    setup_logging("Carrusel 3D", console=True)

    resolution = parse_args(sys.argv[1:])
    if resolution is not None:
        width, height = resolution
        load_prc_file_data("", f"win-size {width} {height}")

    app = App()
    app.run()


if __name__ == "__main__":
    main()
