"""
Carrusel de cajas de juego en arco, estilo navegador de discos de Dreamcast:
las cajas reposan en un arco poco profundo frente a la cámara, la
seleccionada se adelanta y se encara, y todas tienen un balanceo continuo de
"flotación" además del desplazamiento al navegar.
"""
import logging
import math
from dataclasses import dataclass

from direct.interval.IntervalGlobal import LerpPosHprInterval
from panda3d.core import NodePath, Texture

from puntueitor.core.models import Game
from puntueitor.gui3d.case_banner import build_case_banner
from puntueitor.gui3d.case_labels import build_case_labels
from puntueitor.gui3d.game_case import build_case_reflection, build_game_case
from puntueitor.gui3d.store_colors import primary_store_color

logger = logging.getLogger(__name__)

# Geometría del arco. Con más elementos que huecos visibles, los de los
# extremos quedan fuera de cámara — es intencional, como en un carrusel real,
# y con VISIBLE_RADIUS amplio las cajas de los bordes se salen de la pantalla
# a los lados a propósito.
ARC_RADIUS = 6.5

# Separación angular. El hueco entre la seleccionada y sus vecinas inmediatas
# (SELECTED_GAP_DEG) es más ancho que el hueco entre las cajas laterales
# entre sí (SIDE_GAP_DEG) — así se agrupan las de los lados sin tocar el
# espacio alrededor de la seleccionada:  |||||||||  |  |||||||||
SELECTED_GAP_DEG = 11.0
SIDE_GAP_DEG = 6.0

SELECTED_LIFT = 0.05

# Giro de cada caja hacia el centro, independiente de su ángulo de posición
# en el arco: con la cámara alejada, seguir el ángulo de posición para el
# giro (como se hacía antes) da giros exagerados en las cajas más externas.
# Un giro fijo por hueco de distancia da un abanico más controlable.
#
# El signo importa y no es el intuitivo: para una caja a la DERECHA
# (offset>0) girarla con +BOX_TILT_DEG la hace mirar hacia FUERA (+X), no
# hacia el centro — comprobado transformando la normal de reposo (0,-1,0)
# con `NodePath.get_quat().xform(...)`. Para mirar hacia el centro hace
# falta el signo contrario al de `offset`.
BOX_TILT_DEG = 40.0

# Bajado de 0.22 a 0.16 al arreglar el reflejo de la carátula: ese 0.22 se
# ajustó cuando el reflejo solo mostraba el color plano del estuche (la
# carátula reflejada se descartaba entera por culling, ver
# `build_case_reflection`). Con el arte real ya visible, el MISMO alfa pesa
# mucho más en pantalla, así que se compensa a la baja para dejarlo en el
# nivel sutil que se venía pidiendo.
REFLECTION_MAX_ALPHA = 0.16

# Cuánto se adelanta la caja seleccionada, ampliando su radio (no
# reduciéndolo). La cámara está detrás del centro del arco (en -Y), así que
# el punto más cercano a ella para un radio dado es el de ángulo 0: reducir
# el radio ahí la ACERCA al centro del arco pero la ALEJA de la cámara. Se
# comprobó en runtime: con el radio reducido la seleccionada quedaba a 5.2
# unidades de la cámara y sus vecinas (radio completo, ±16°) a 4.6 — la
# seleccionada salía más lejos, y por tanto más pequeña, que las de al lado.
SELECTED_FORWARD = 0.9

# Cuántas cajas se muestran a cada lado de la seleccionada. Con más juegos
# que huecos visibles, el arco daría más de una vuelta completa y las cajas
# se solaparían entre sí — así que el resto se oculta y solo se "revela" al
# entrar en este radio al navegar (virtualización simple, sin recorrer toda
# la biblioteca en pantalla a la vez).
VISIBLE_RADIUS = 4

SLIDE_DURATION = 0.28

# Balanceo continuo ("Dreamcast"): una oscilación suave e independiente por
# caja para que el carrusel nunca esté del todo quieto.
#
# La caja SELECCIONADA solo sube y baja, no se balancea: es la que se está
# mirando y la que manda el título y la descripción, y con el balanceo
# puesto costaba leerla. Las de los lados lo conservan, que es lo que
# mantiene vivo el conjunto. El sube-y-baja es idéntico en las dos.
IDLE_BOB_AMPLITUDE = 0.05
IDLE_BOB_PERIOD = 3.2
IDLE_ROCK_AMPLITUDE_DEG = 2.5

# En cuánto tiempo entra o sale el balanceo al cambiar de selección. Sin
# esta transición, al navegar la caja que deja de estar seleccionada
# recupera el balanceo de golpe (hasta IDLE_ROCK_AMPLITUDE_DEG de salto
# instantáneo) y la que pasa a estarlo lo pierde igual de bruscamente. Va
# igualado a SLIDE_DURATION para que ocurra dentro del mismo movimiento de
# navegación y no se perciba como un paso aparte.
ROCK_BLEND_DURATION = SLIDE_DURATION


def _cumulative_angle(distance: int) -> float:
    """
    Ángulo acumulado (sin signo) hasta el hueco a `distance` posiciones de
    la seleccionada: el primer salto usa `SELECTED_GAP_DEG`, cada uno
    después usa el hueco más ajustado `SIDE_GAP_DEG` — así las cajas
    laterales se agrupan entre sí sin tocar el espacio junto a la
    seleccionada.
    """
    if distance <= 0:
        return 0.0
    return SELECTED_GAP_DEG + (distance - 1) * SIDE_GAP_DEG


@dataclass(frozen=True)
class CarouselEntry:
    """
    Los datos que el carrusel necesita de un juego.

    El carrusel en sí solo usa `key`, `texture` y `stores` — el resto va de
    paso, para que quien dibuja el título y la ficha lo tenga a mano sin
    tener que volver a consultar la biblioteca en cada movimiento.
    """
    key: object  # normalmente igdb_id; opaco para el carrusel
    title: str
    texture: Texture
    stores: frozenset = frozenset()
    game: Game | None = None  # ficha completa; None con datos incompletos


class CarouselBox:
    """Una caja del carrusel y su fase de animación idle."""

    def __init__(self, parent: NodePath, entry: CarouselEntry, phase: float):
        self.entry = entry
        self.phase = phase  # desfase para que no todas floten al unísono
        self.root = parent.attach_new_node(f"case-{entry.key}")
        body_color = primary_store_color(entry.stores)
        _case_np, self.cover_np = build_game_case(self.root, body_color=body_color)
        self.cover_np.set_texture(entry.texture)
        _reflection_root, self.reflection_cover_np = build_case_reflection(
            self.root, max_alpha=REFLECTION_MAX_ALPHA, body_color=body_color,
        )
        self.reflection_cover_np.set_texture(entry.texture)
        self.texture = entry.texture
        build_case_banner(self.root, entry.stores)
        self.labels_np = build_case_labels(self.root, entry.game)
        self._base_pos = self.root.get_pos()
        self._base_hpr = self.root.get_hpr()
        self._slide: LerpPosHprInterval | None = None
        # 0 = sin balanceo (caja seleccionada), 1 = balanceo completo.
        self._rock_blend = 1.0

    def set_texture(self, texture: Texture) -> None:
        """
        Sustituye la carátula en caliente (p.ej. al llegar una descarga).
        `entry.texture` es inmutable (CarouselEntry es frozen); esta es la
        textura "actual" real, la que hay que consultar tras una descarga.
        """
        self.cover_np.set_texture(texture)
        self.reflection_cover_np.set_texture(texture)
        self.texture = texture

    def rebuild_labels(self, game, visible: bool = True) -> None:
        """
        Rehace las pegatinas de estado tras cambiar un dato del juego.

        Se tiran y se vuelven a construir en vez de esconder o enseñar las
        que ya hay: qué pegatinas existen y en qué hueco va cada una depende
        de la combinación de estados (terminado y backlog comparten columna,
        ver `case_labels`), así que no hay una correspondencia fija entre
        campo y nodo que se pueda ir tocando.

        `visible` mantiene el estado del interruptor global de etiquetas: si
        estaban ocultas, las nuevas tienen que nacer ocultas también.
        """
        if self.labels_np is not None:
            self.labels_np.remove_node()
        self.labels_np = build_case_labels(self.root, game)
        if self.labels_np is not None and not visible:
            self.labels_np.hide()

    def set_slot(self, angle_deg: float, tilt_deg: float, selected: bool) -> None:
        """Posiciona la caja en su hueco del arco (sin animar)."""
        if self._slide is not None and not self._slide.is_stopped():
            self._slide.finish()

        radius = ARC_RADIUS + (SELECTED_FORWARD if selected else 0.0)
        angle = math.radians(angle_deg)
        x = radius * math.sin(angle)
        y = -radius * math.cos(angle)
        z = SELECTED_LIFT if selected else 0.0

        self.root.set_pos(x, y, z)
        self.root.set_hpr(tilt_deg, 0, 0)
        self._base_pos = self.root.get_pos()
        self._base_hpr = self.root.get_hpr()
        # Sin animar: el balanceo se ajusta de golpe, igual que la posición.
        # Si no, la caja seleccionada al arrancar nacería balanceándose y se
        # quedaría quieta sola durante el primer cuarto de segundo.
        self._rock_blend = 0.0 if selected else 1.0

    def slide_to_slot(self, angle_deg: float, tilt_deg: float, selected: bool) -> None:
        """
        Interpolación suave hacia un nuevo hueco del arco. Arranca y se
        gestiona a sí misma: no depende de que el llamante la agrupe ni la
        arranque (ver nota en la clase `Carousel` sobre por qué se dejó de
        usar `Parallel` para esto).

        Si ya había una interpolación en curso (navegación más rápida que
        SLIDE_DURATION, típica con auto-repeat de teclado/mando) se fuerza a
        su posición final antes de lanzar la nueva. Sin esto, dos
        `LerpPosHprInterval` solapadas sobre el mismo nodo escriben pos/hpr
        cada una a su ritmo y el resultado visual es errático.
        """
        if self._slide is not None and not self._slide.is_stopped():
            self._slide.finish()

        radius = ARC_RADIUS + (SELECTED_FORWARD if selected else 0.0)
        angle = math.radians(angle_deg)
        x = radius * math.sin(angle)
        y = -radius * math.cos(angle)
        z = SELECTED_LIFT if selected else 0.0

        target_pos = (x, y, z)
        target_hpr = (tilt_deg, 0, 0)
        self._slide = LerpPosHprInterval(
            self.root, SLIDE_DURATION, target_pos, target_hpr,
        )
        self._slide.start()
        self._base_pos = target_pos
        self._base_hpr = target_hpr

    def apply_idle(self, elapsed: float, dt: float, rocking: bool) -> None:
        """
        Balanceo continuo de flotación, superpuesto a la posición base.

        `rocking` a False deja solo el sube-y-baja vertical, sin giro — es
        lo que se usa con la caja seleccionada. El sube-y-baja no cambia:
        misma amplitud, mismo periodo y misma fase en los dos casos.
        """
        target = 1.0 if rocking else 0.0
        step = dt / ROCK_BLEND_DURATION if ROCK_BLEND_DURATION > 0 else 1.0
        if self._rock_blend < target:
            self._rock_blend = min(target, self._rock_blend + step)
        else:
            self._rock_blend = max(target, self._rock_blend - step)

        t = elapsed / IDLE_BOB_PERIOD + self.phase
        bob = math.sin(t * 2 * math.pi) * IDLE_BOB_AMPLITUDE
        rock = math.sin(t * 2 * math.pi * 0.5) * IDLE_ROCK_AMPLITUDE_DEG * self._rock_blend

        self.root.set_z(self._base_pos[2] + bob)
        self.root.set_r(self._base_hpr[2] + rock)


class Carousel:
    """
    Gestiona un conjunto de `CarouselBox` dispuestas en arco y la navegación
    entre ellas.
    """

    def __init__(self, parent: NodePath, entries: list[CarouselEntry]):
        if not entries:
            raise ValueError("Carousel requiere al menos un juego")

        self._parent = parent
        self._entries = entries
        self._boxes = [
            CarouselBox(parent, entry, phase=i / max(len(entries), 1))
            for i, entry in enumerate(entries)
        ]
        self._boxes_by_key = {box.entry.key: box for box in self._boxes}

        # `_order` son los índices de las cajas que se recorren AHORA MISMO,
        # en el orden en que se recorren, y `_selected_pos` es una posición
        # DENTRO de `_order` — no un índice de `_boxes`. Esa indirección es
        # la que permite filtrar (ocultar juegos marcados como ocultos) y,
        # el día que se conecte, reordenar, sin reconstruir nada: las cajas
        # se construyen una sola vez (1,2 s y ~270 MB con la biblioteca
        # real), así que rehacerlas en cada cambio de filtro daría un tirón
        # de más de un segundo por pulsación.
        self._order = list(range(len(entries)))
        self._pos_by_key = {entry.key: i for i, entry in enumerate(entries)}
        self._selected_pos = 0
        self._elapsed = 0.0
        self._layout(animate=False)

    def set_texture(self, key: object, texture: Texture) -> None:
        """Actualiza la carátula del juego `key`, si sigue en el carrusel."""
        box = self._boxes_by_key.get(key)
        if box is not None:
            box.set_texture(texture)

    def rebuild_labels(self, key: object, game, visible: bool = True) -> None:
        """Rehace las pegatinas del juego `key`, si sigue en el carrusel."""
        box = self._boxes_by_key.get(key)
        if box is not None:
            box.rebuild_labels(game, visible)

    def set_labels_visible(self, visible: bool) -> None:
        """
        Muestra u oculta las etiquetas de TODAS las cajas a la vez.

        Se recorren todas, no solo las visibles: una caja fuera del radio
        visible acabará entrando al navegar, y si no se le hubiera aplicado
        el estado aparecería con las etiquetas puestas después de haberlas
        ocultado.
        """
        for box in self._boxes:
            if box.labels_np is None:
                continue  # juego sin ninguna etiqueta que enseñar
            if visible:
                box.labels_np.show()
            else:
                box.labels_np.hide()

    # ──────────────────────────────
    # Navegación
    # ──────────────────────────────

    @property
    def _selected_box_index(self) -> int:
        """Índice en `_boxes` de la caja seleccionada."""
        return self._order[self._selected_pos]

    @property
    def selected(self) -> CarouselEntry:
        return self._entries[self._selected_box_index]

    @property
    def selected_texture(self) -> Texture:
        """
        Textura realmente aplicada a la caja seleccionada ahora mismo — a
        diferencia de `selected.texture`, refleja las descargas en caliente
        aplicadas vía `set_texture` (ver `CarouselBox.set_texture`).
        """
        return self._boxes[self._selected_box_index].texture

    @property
    def visible_count(self) -> int:
        """Cuántos juegos se pueden recorrer ahora mismo."""
        return len(self._order)

    def move(self, direction: int) -> None:
        """direction: -1 (izquierda) o +1 (derecha)."""
        if len(self._order) <= 1:
            return
        self._selected_pos = (self._selected_pos + direction) % len(self._order)
        self._layout(animate=True)

    def neighbour_entries(self, radius: int) -> list[CarouselEntry]:
        """
        Las entradas visibles a `radius` huecos o menos de la seleccionada.

        Lo resuelve el carrusel, no quien llama, porque la vecindad depende
        del orden VISIBLE: con juegos filtrados, dos entradas contiguas en
        la lista completa pueden estar a decenas de huecos una de otra, o
        no estar. Quien precarga carátulas quiere las que el usuario va a
        alcanzar navegando, que son estas.
        """
        total = len(self._order)
        if not total:
            return []
        radius = min(radius, total // 2)
        return [
            self._entries[self._order[(self._selected_pos + offset) % total]]
            for offset in range(-radius, radius + 1)
        ]

    def is_near_selection(self, key: object, radius: int) -> bool:
        """¿Está `key` visible y a `radius` huecos o menos de la selección?"""
        pos = self._pos_by_key.get(key)
        if pos is None:
            return False
        total = len(self._order)
        offset = (pos - self._selected_pos) % total
        return min(offset, total - offset) <= radius

    def set_visible_keys(self, keys: set) -> None:
        """
        Restringe el carrusel a `keys`, conservando el orden base.

        Se reconstruye el recorrido a partir de la lista completa, así que
        un juego que vuelve a aparecer lo hace EN SU SITIO (por orden
        alfabético, o el que imponga la ordenación cuando se conecte), no
        al final.

        Si no quedara ningún juego visible no se aplica nada: el carrusel
        no tiene un estado "vacío" que dibujar y medio programa da por hecho
        que hay una selección (la ficha, el fondo, el menú de juego). Es
        preferible ignorar el filtro y avisar que quedarse sin selección.
        """
        order = [i for i, entry in enumerate(self._entries) if entry.key in keys]
        if not order:
            logger.warning(
                "gui3d: el filtro dejaría el carrusel vacío; se ignora"
            )
            return

        previous_key = self.selected.key
        previous_box_index = self._selected_box_index

        visible = set(order)
        for index, box in enumerate(self._boxes):
            if index not in visible:
                box.root.hide()

        self._order = order
        self._pos_by_key = {
            self._entries[index].key: pos for pos, index in enumerate(order)
        }

        # Se intenta seguir en el mismo juego. Si es el que acaba de dejar
        # de verse (te ocultas el juego que tienes delante), se cae al
        # siguiente que sí se vea a partir de donde estabas, que es lo que
        # menos desorienta: la selección se queda donde estaba mirando el
        # usuario en vez de saltar al principio de la biblioteca.
        pos = self._pos_by_key.get(previous_key)
        if pos is None:
            pos = next(
                (p for p, index in enumerate(order) if index >= previous_box_index),
                0,
            )
        self._selected_pos = pos

        self._layout(animate=False)

    def update(self, dt: float) -> None:
        """Llamar cada frame: avanza el balanceo continuo de las cajas."""
        self._elapsed += dt
        selected = self._selected_box_index
        for i, box in enumerate(self._boxes):
            box.apply_idle(self._elapsed, dt, rocking=i != selected)

    # ──────────────────────────────
    # Interno
    # ──────────────────────────────

    def _layout(self, animate: bool) -> None:
        """
        Recalcula el ángulo de cada caja relativo a la seleccionada.

        Cada `CarouselBox` arranca y cancela su propia interpolación (ver
        `CarouselBox.slide_to_slot`); agruparlas antes en un `Parallel` por
        cada navegación dejaba `Parallel`s huérfanos vivos en el gestor de
        intervalos si el usuario navegaba más rápido que SLIDE_DURATION, que
        seguían intentando animar cajas ya finalizadas por otra vía.
        """
        n = len(self._order)

        # Se recorre el orden VISIBLE, no todas las cajas: las filtradas ya
        # las escondió `set_visible_keys` y no tienen hueco en el arco.
        for pos, box_index in enumerate(self._order):
            box = self._boxes[box_index]
            offset = self._signed_offset(pos, n)

            if abs(offset) > VISIBLE_RADIUS:
                box.root.hide()
                continue

            angle_deg = math.copysign(_cumulative_angle(abs(offset)), offset)
            # Fijo, no acumulativo: todas las cajas no seleccionadas giran lo
            # mismo hacia el centro, sin importar a cuántos huecos estén —
            # multiplicar por offset (como con angle_deg) dejaba las cajas
            # más externas casi de canto (120°+ a partir del tercer hueco).
            # Signo invertido respecto a offset: ver nota en BOX_TILT_DEG.
            tilt_deg = math.copysign(BOX_TILT_DEG, -offset) if offset else 0.0
            selected = offset == 0
            entering = box.root.is_hidden()
            box.root.show()

            if animate and not entering:
                box.slide_to_slot(angle_deg, tilt_deg, selected)
            else:
                # Instantáneo si la caja acaba de entrar en el radio visible:
                # deslizarla desde su última posición (fuera de pantalla,
                # potencialmente al otro lado del arco) se vería como un
                # salto cruzando toda la pantalla.
                box.set_slot(angle_deg, tilt_deg, selected)

    def _signed_offset(self, index: int, n: int) -> int:
        """Distancia con signo más corta de `index` a la caja seleccionada."""
        raw = index - self._selected_pos
        half = n / 2.0
        if raw > half:
            raw -= n
        elif raw < -half:
            raw += n
        return raw
