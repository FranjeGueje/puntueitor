"""
Frontend 3D de Puntueitor: carrusel de cajas de juego con ficha, navegable
con teclado o mando.

Alternativa a la TUI (`gui/`), no un reemplazo: las dos leen la misma
biblioteca cacheada y ninguna toca `core/`. Es solo lectura — no lanza el
pipeline ni pide nada a IGDB; lo único que baja de la red son las carátulas
que falten, y en segundo plano.

Ejecutar con:
    python -m puntueitor.gui3d.app
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
from puntueitor.gui3d.ficha import FIELD_LABELS, build_description, build_values
from puntueitor.gui3d.gamepad_input import GamepadInput
from puntueitor.gui3d.real_data import build_real_entries
from puntueitor.gui3d.sample_data import build_sample_entries
from puntueitor.gui3d.submenu import Submenu

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
FICHA_BAR_TOP_Z = -0.36

FICHA_LABEL_SCALE = 0.030
FICHA_LINE_HEIGHT = 0.042
FICHA_TOP_MARGIN = 0.070
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
DESCRIPTION_TEXT_SCALE = 0.036

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

SUBMENU_OPTIONS = ["Ordenar", "Filtrar", "Configurar", "Enriquecedores", "Salir"]

# Cuánto se sube el carrusel entero para que quede pegado al título.
CAROUSEL_RAISE = 1.3

BACKGROUND_COLOR = (0.04, 0.04, 0.06, 1)

HELP_TEXT = (
    "<-  /  ->  o mando: navegar   -   Enter/A: seleccionar   -   "
    "Esc/Start: menu   -   Q: salir"
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

        raw_entries, pending_downloads = build_real_entries() or build_sample_entries()
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

        self._on_selection_changed()

        self.submenu = Submenu(self.aspect2d, SUBMENU_OPTIONS)

        self._setup_keyboard()
        self.gamepad = GamepadInput(
            self,
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
        # Alejada respecto a la primera versión (-8.5) para que el carrusel
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
                align=TextNode.A_right, mayChange=False,
            ))
            self.ficha_value_texts.append(OnscreenText(
                parent=self.ficha_frame, text="", pos=(0, 0),
                scale=FICHA_LABEL_SCALE, fg=FICHA_VALUE_COLOR,
                align=TextNode.A_left, mayChange=True,
            ))

        self.description_text = OnscreenText(
            parent=self.ficha_frame, text="", pos=(0, 0),
            scale=DESCRIPTION_TEXT_SCALE, fg=(0.86, 0.86, 0.89, 1),
            align=TextNode.A_left, wordwrap=40, mayChange=True,
        )
        self.help_text = OnscreenText(
            parent=self.ficha_frame, text=HELP_TEXT,
            pos=(0, -0.955), scale=0.032,
            fg=(0.55, 0.55, 0.6, 1), align=TextNode.A_center, mayChange=False,
        )

        self._resize_ficha()

    def _on_window_event(self, window) -> None:
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
        # `_held_direction`.
        self._keys_held = {"left": False, "right": False}
        for key, name in (("arrow_left", "left"), ("arrow_right", "right")):
            self.accept(key, self._set_key_held, [name, True])
            self.accept(f"{key}-up", self._set_key_held, [name, False])

        self.accept("enter", self._on_confirm)
        self.accept("escape", self._on_back)
        self.accept("q", self.userExit)

    def _set_key_held(self, name: str, held: bool) -> None:
        self._keys_held[name] = held

    def _navigate(self, direction: int) -> None:
        """Un paso a izquierda (-1) o derecha (+1)."""
        if self.submenu.is_open:
            self.submenu.move_focus(direction)
        else:
            self.carousel.move(direction)
            self._on_selection_changed()

    def _held_direction(self) -> int:
        """
        Dirección que se está pidiendo ahora mismo, de teclado o de mando.

        Se lee como ESTADO en vez de reaccionar a eventos de pulsación,
        porque un evento no dice si la tecla sigue abajo. Se podría usar el
        auto-repeat del sistema (Panda3D emite "arrow_left-repeat"), pero su
        cadencia la fija el escritorio del usuario y no tiene por qué pegar
        con un carrusel; con el estado, el ritmo lo decidimos aquí y sale
        igual en teclado y en mando.
        """
        direction = (1 if self._keys_held["right"] else 0) - (
            1 if self._keys_held["left"] else 0
        )
        if direction:
            return direction
        return self.gamepad.direction() if self.gamepad else 0

    def _update_navigation(self, dt: float) -> None:
        direction = self._held_direction()

        if direction != self._nav_direction:
            self._nav_direction = direction
            self._nav_held_time = 0.0
            self._nav_next_repeat = NAV_REPEAT_DELAY
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
        """
        while self._pending_covers and self.cover_loader.inflight < COVER_BACKFILL_INFLIGHT:
            key, pending = self._pending_covers.popitem()
            self.cover_loader.request(key, *pending)

    def _request_nearby_covers(self) -> None:
        """
        Encola la descarga de las carátulas que faltan alrededor de la
        selección, y solo esas.

        El radio es más ancho que `VISIBLE_RADIUS` a propósito, para que la
        carátula de una caja llegue antes de que el usuario se plante en
        ella. Cada clave se pide una sola vez: se saca del diccionario al
        pedirla, y `CoverLoader` además ignora las repetidas.
        """
        total = len(self.entries)
        if not self._pending_covers or not total:
            return

        center = self.carousel.selected_index
        for offset in range(-COVER_PRELOAD_RADIUS, COVER_PRELOAD_RADIUS + 1):
            entry = self.entries[(center + offset) % total]
            pending = self._pending_covers.pop(entry.key, None)
            if pending is not None:
                self.cover_loader.request(entry.key, *pending)

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
        self._check_lens_aspect_ratio()

        dt = globalClock.get_dt()
        self._update_navigation(dt)
        self.carousel.update(dt)

        for key, texture in self.cover_loader.poll():
            self.carousel.set_texture(key, texture)

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
        self.cover_loader.shutdown()
        self.gamepad.destroy()
        super().destroy()


def main() -> None:
    app = App()
    app.run()


if __name__ == "__main__":
    main()
