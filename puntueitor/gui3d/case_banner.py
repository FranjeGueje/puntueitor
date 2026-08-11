"""
Banner de tiendas incrustado en la parte superior de cada caja del carrusel
— geometría pegada al frente del estuche (mismo patrón que la carátula en
`game_case.py`), no un panel aparte flotando sobre la escena. Se mueve, gira
y se balancea con la caja porque es un hijo más de su nodo.

No hay logos reales de Steam/Epic/GOG/Amazon en el repo — usar los oficiales
sin más plantea temas de marca para algo que no es material oficial
de esas tiendas. Cada badge es un color distintivo + texto corto en vez del
logo — la misma paleta que `store_colors.py` usa para el color del estuche y
`real_data.py` para la carátula de relleno, un solo sitio para las tres.
"""
import math

from panda3d.core import (
    CardMaker,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    TextNode,
)

from puntueitor.core.models import Stores
from puntueitor.gui3d.game_case import (
    BANNER_HEIGHT,
    CASE_DEPTH,
    CASE_HEIGHT,
    CASE_WIDTH,
    CORNER_SEGMENTS,
    inner_size,
)
from puntueitor.gui3d.store_colors import STORE_COLORS, STORE_PRIORITY

NAVY = (0.03, 0.07, 0.18, 1.0)

CHIP_GAP = 0.018
CHIP_PADDING_V = 0.014
TEXT_SCALE = 0.042

_STORE_ORDER = STORE_PRIORITY
_STORE_LABELS = {
    Stores.STEAM: "STEAM",
    Stores.GOG: "GOG",
    Stores.EPIC: "EPIC",
    Stores.AMAZON: "AMZN",
}
_CHIP_WIDTH = {store: 0.028 * len(label) + 0.05 for store, label in _STORE_LABELS.items()}


def _chip_color(store: Stores) -> tuple[float, float, float, float]:
    r, g, b = STORE_COLORS[store]
    return (r, g, b, 1.0)


def _flat_card(parent: NodePath, x0, x1, z0, z1, y: float, color) -> NodePath:
    card = CardMaker("banner-chip")
    card.set_frame(x0, x1, z0, z1)
    card.set_color(*color)
    node = parent.attach_new_node(card.generate())
    node.set_pos(0, y, 0)
    node.set_light_off()
    return node


def _rounded_top_outline(
    width: float, z_bottom: float, z_top: float, radius: float, segments: int,
) -> list[tuple[float, float]]:
    """
    Contorno de un rectángulo con solo las esquinas SUPERIORES redondeadas
    (las inferiores, rectas) en el plano XZ, antihorario empezando por la
    esquina inferior derecha — se le pasa el radio del área interior, para
    que el banner encaje exactamente en la parte superior de la carátula en
    vez de que sus picos asomen por fuera de la silueta redondeada.
    """
    hw = width / 2.0
    r = min(radius, hw, z_top - z_bottom)

    points = [(hw, z_bottom)]

    cx, cz = hw - r, z_top - r
    for i in range(segments + 1):  # arco superior derecho: 0° -> 90°
        angle = math.radians(90.0 * i / segments)
        points.append((cx + r * math.cos(angle), cz + r * math.sin(angle)))

    cx = -hw + r
    for i in range(segments + 1):  # arco superior izquierdo: 90° -> 180°
        angle = math.radians(90.0 + 90.0 * i / segments)
        points.append((cx + r * math.cos(angle), cz + r * math.sin(angle)))

    points.append((-hw, z_bottom))
    return points


def _build_banner_background(
    width: float, z_bottom: float, z_top: float, radius: float,
    color: tuple[float, float, float, float],
) -> NodePath:
    """Fondo navy del banner, con las esquinas superiores redondeadas."""
    outline = _rounded_top_outline(width, z_bottom, z_top, radius, CORNER_SEGMENTS)
    cz = (z_bottom + z_top) / 2.0

    fmt = GeomVertexFormat.get_v3n3c4()
    vdata = GeomVertexData("banner-bg", fmt, Geom.UH_static)
    vertex_w = GeomVertexWriter(vdata, "vertex")
    normal_w = GeomVertexWriter(vdata, "normal")
    color_w = GeomVertexWriter(vdata, "color")
    triangles = GeomTriangles(Geom.UH_static)

    center_row = vertex_w.get_write_row()
    vertex_w.add_data3(0, 0, cz)
    normal_w.add_data3(0, -1, 0)
    color_w.add_data4(*color)

    start_row = vertex_w.get_write_row()
    for x, z in outline:
        vertex_w.add_data3(x, 0, z)
        normal_w.add_data3(0, -1, 0)
        color_w.add_data4(*color)

    n = len(outline)
    for i in range(n):
        a = start_row + i
        b = start_row + (i + 1) % n
        triangles.add_vertices(center_row, a, b)

    geom = Geom(vdata)
    geom.add_primitive(triangles)
    node = GeomNode("banner-bg")
    node.add_geom(geom)

    return NodePath(node)


def build_case_banner(
    parent: NodePath,
    stores: frozenset,
    width: float = CASE_WIDTH,
    height: float = CASE_HEIGHT,
    depth: float = CASE_DEPTH,
) -> NodePath | None:
    """
    Construye el banner de tiendas de una caja. Devuelve None (sin crear
    nada) si el juego no tiene ninguna tienda asociada.
    """
    present = [s for s in _STORE_ORDER if s in stores]
    if not present:
        return None

    root = parent.attach_new_node("store-banner")

    # Ocupa la franja de arriba del ÁREA INTERIOR del estuche, no el borde
    # exterior: antes iba pegado al borde y a todo el ancho del estuche, así
    # que se comía el marco por arriba y por los lados. Compartiendo ancho y
    # radio de esquina con el área interior, el marco queda continuo
    # alrededor del conjunto banner + carátula.
    #
    # Y la carátula empieza justo DEBAJO de esta franja, sin solaparse: el
    # alto del estuche está calculado para que las dos quepan enteras (ver
    # CASE_HEIGHT en `game_case.py`).
    inner_w, inner_h, radius = inner_size(width, height)

    z_top = inner_h / 2
    z_bottom = z_top - BANNER_HEIGHT
    banner_y = -depth / 2 - 0.004  # ligeramente por delante de la carátula

    bg_np = _build_banner_background(inner_w, z_bottom, z_top, radius, NAVY)
    bg_np.reparent_to(root)
    bg_np.set_pos(0, banner_y, 0)
    bg_np.set_light_off()

    widths = [_CHIP_WIDTH[s] for s in present]
    total_width = sum(widths) + CHIP_GAP * (len(present) - 1)
    chip_z0 = z_bottom + CHIP_PADDING_V
    chip_z1 = z_top - CHIP_PADDING_V
    chip_y = banner_y - 0.001

    x = -total_width / 2
    for store, chip_width in zip(present, widths):
        _flat_card(root, x, x + chip_width, chip_z0, chip_z1, chip_y, _chip_color(store))

        label = TextNode(f"banner-label-{store.value}")
        label.set_text(_STORE_LABELS[store])
        label.set_align(TextNode.A_center)
        label.set_text_color(1, 1, 1, 1)
        label_np = root.attach_new_node(label)
        label_np.set_light_off()
        label_np.set_scale(TEXT_SCALE)
        label_np.set_pos(
            x + chip_width / 2,
            chip_y - 0.001,
            (chip_z0 + chip_z1) / 2 - TEXT_SCALE * 0.32,
        )
        x += chip_width + CHIP_GAP

    return root
