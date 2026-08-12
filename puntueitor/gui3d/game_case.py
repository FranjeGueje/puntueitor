"""
Nodo 3D de una "caja de juego" física: un prisma delgado de esquinas
redondeadas (el estuche) con la carátula pegada a la cara frontal como una
tarjeta independiente, recortada al mismo contorno redondeado.

Panda3D aplica una textura a todo un `Geom`, así que texturizar solo una cara
de una caja con vértices compartidos requeriría vértices duplicados y varios
`Geom` con distinto `RenderState` dentro del mismo nodo. Es más simple —y es
exactamente como es un estuche real— separar el cuerpo (color sólido, sin
textura) de la carátula (una tarjeta con la textura) como dos NodePaths
independientes bajo el mismo padre.
"""
import math
from collections.abc import Callable

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    Texture,
    TransparencyAttrib,
)

CASE_WIDTH = 1.0

# Proporción (ancho/alto) del ARTE de la carátula: la de una carátula de
# videojuego estándar, aprox. 3:4 vertical. Es lo que hay que preservar,
# porque cualquier desviación estira o achata el arte de forma visible.
COVER_ASPECT = 1.0 / 1.33

# Alto de la franja de tiendas, pegada a la parte de arriba del área
# interior. Vive aquí, y no en `case_banner.py`, porque la altura total del
# estuche depende de ella (ver CASE_HEIGHT) y al revés sería un import
# circular entre los dos módulos.
BANNER_HEIGHT = 0.11

# Más grueso que un estuche real a escala (que sería ~0.06) a propósito: a
# la distancia de cámara del carrusel, el lomo fino se volvía casi
# imperceptible en cuanto las cajas giraban hacia el centro y quedaban más
# juntas entre sí — se confirmó que la geometría SÍ estaba ahí (posición y
# bounds correctos) renderizando con los parámetros reales del carrusel, solo
# que a un grosor casi de 1 píxel. Esto no cambia las proporciones de la
# carátula (CASE_WIDTH/CASE_HEIGHT), solo lo grueso que se ve el lomo.
CASE_DEPTH = 0.13

CASE_BODY_COLOR = (0.08, 0.08, 0.09)

# Radio de las esquinas redondeadas y suavidad del arco (más segmentos =
# curva más lisa; 6 por esquina ya es indistinguible de una curva perfecta
# a la distancia a la que se ve la caja, y son solo 24 puntos de contorno).
CORNER_RADIUS = 0.06
CORNER_SEGMENTS = 6

# Cuánto sobresale la carátula de la cara frontal del estuche, para evitar
# z-fighting entre la tarjeta y el cuerpo de la caja.
_COVER_OFFSET = 0.002

# Margen del estuche visible alrededor de la carátula, como fracción del
# tamaño del estuche. Antes la carátula medía EXACTAMENTE lo mismo que el
# estuche, así que de frente lo tapaba al 100% y del estuche no se veía nada
# más que un lomo de pocos píxeles: el carrusel parecía una fila de láminas
# planas flotando, no de cajas ("no se ven las cajas, solo los covers").
# Con la carátula metida hacia dentro, el cuerpo asoma como un marco de
# color alrededor — que además es justo donde se ve el color de la tienda.
#
# Se aplica como FRACCIÓN, no como número fijo de unidades, a propósito: un
# margen fijo en X y Z cambiaría la relación de aspecto del área interior y,
# con ella, la del arte. Escalando ambos ejes por el mismo factor, la
# proporción se mantiene exacta.
COVER_INSET = 0.026

_INSET_SCALE = 1.0 - 2.0 * COVER_INSET

# La altura del estuche NO es un número elegido a mano, se deduce del resto:
# el área interior tiene que dar de sí para la franja del banner MÁS una
# carátula con la proporción exacta de COVER_ASPECT debajo, sin que se pisen.
#
# Es geometría, no hay margen de elección: con marco uniforme, banner que no
# solapa la carátula y arte sin deformar, el estuche tiene que ser más alto
# que el arte. Que es justo como es un estuche físico de verdad — la banda
# del título va por encima de la portada, no encima de ella — y por qué esto
# sale en 1:1.45, más cerca de la proporción de una caja de DVD real (1:1.41)
# que el 1:1.33 de antes, que era la del arte a secas.
_INNER_WIDTH = CASE_WIDTH * _INSET_SCALE
_COVER_HEIGHT = _INNER_WIDTH / COVER_ASPECT
CASE_HEIGHT = (_COVER_HEIGHT + BANNER_HEIGHT) / _INSET_SCALE

# Alfa constante: la usan tanto la caja real como la carátula real (no el
# reflejo, que usa un desvanecimiento por altura en su lugar).
_OPAQUE: Callable[[float], float] = lambda z: 1.0


def _rounded_rect_outline(
    width: float, height: float, radius: float, segments: int,
    top_radius: float | None = None,
) -> list[tuple[float, float, float, float]]:
    """
    Contorno de un rectángulo de esquinas redondeadas en el plano XZ, como
    lista de (x, z, nx, nz) — posición y normal 2D saliente en ese punto.

    Trazado antihorario visto desde -Y (mismo criterio que el resto del
    módulo), empezando por el extremo inferior del arco de la esquina
    inferior derecha. La normal de un punto sobre un arco es simplemente su
    propia dirección radial desde el centro de ESE arco; en los tramos
    rectos entre esquinas, el punto inicial y final de los arcos contiguos
    ya caen exactamente en la normal del tramo recto (comprobado: el punto
    final del arco inferior-derecha y el inicial del arco superior-derecha
    coinciden en (1, 0), la normal correcta del lomo derecho), así que no
    hacen falta puntos ni normales aparte para los tramos rectos.
    """
    hw, hh = width / 2.0, height / 2.0
    rb = min(radius, hw, hh)
    rt = rb if top_radius is None else min(top_radius, hw, hh)

    # (centro del arco, ángulo inicial en grados, radio), antihorario
    # empezando por la esquina inferior derecha.
    corners = (
        (hw - rb, -hh + rb, -90.0, rb),   # inferior derecha
        (hw - rt, hh - rt, 0.0, rt),      # superior derecha
        (-hw + rt, hh - rt, 90.0, rt),    # superior izquierda
        (-hw + rb, -hh + rb, 180.0, rb),  # inferior izquierda
    )

    points: list[tuple[float, float, float, float]] = []
    for cx, cz, start_deg, r in corners:
        if r <= 0.0:
            # Esquina viva: un solo punto, con la normal de la bisectriz.
            # La usa la carátula, cuyo borde superior tiene que quedar a
            # ras con el borde inferior (recto) del banner; si fuera
            # redondeado asomarían dos muescas de color de estuche justo
            # debajo de las puntas del banner.
            angle = math.radians(start_deg + 45.0)
            nx, nz = math.cos(angle), math.sin(angle)
            points.append((cx, cz, nx, nz))
            continue
        for i in range(segments + 1):
            angle = math.radians(start_deg + 90.0 * i / segments)
            nx, nz = math.cos(angle), math.sin(angle)
            points.append((cx + r * nx, cz + r * nz, nx, nz))
    return points


def _add_cap(
    vertex_w: GeomVertexWriter,
    normal_w: GeomVertexWriter,
    color_w: GeomVertexWriter,
    triangles: GeomTriangles,
    outline: list[tuple[float, float, float, float]],
    y: float,
    face_normal: tuple[float, float, float],
    color_rgb: tuple[float, float, float],
    alpha_for_z: Callable[[float], float],
    reverse: bool,
) -> None:
    """Tapa (frontal o trasera) del estuche: abanico de triángulos desde el centro."""
    r, g, b = color_rgb

    center_row = vertex_w.get_write_row()
    vertex_w.add_data3(0, y, 0)
    normal_w.add_data3(*face_normal)
    color_w.add_data4(r, g, b, alpha_for_z(0.0))

    start_row = vertex_w.get_write_row()
    for x, z, _nx, _nz in outline:
        vertex_w.add_data3(x, y, z)
        normal_w.add_data3(*face_normal)
        color_w.add_data4(r, g, b, alpha_for_z(z))

    n = len(outline)
    for i in range(n):
        a = start_row + i
        b_ = start_row + (i + 1) % n
        if reverse:
            triangles.add_vertices(center_row, b_, a)
        else:
            triangles.add_vertices(center_row, a, b_)


def _add_belt(
    vertex_w: GeomVertexWriter,
    normal_w: GeomVertexWriter,
    color_w: GeomVertexWriter,
    triangles: GeomTriangles,
    outline: list[tuple[float, float, float, float]],
    hd: float,
    color_rgb: tuple[float, float, float],
    alpha_for_z: Callable[[float], float],
) -> None:
    """Banda lateral: conecta el contorno frontal con el trasero, siguiendo la curva."""
    r, g, b = color_rgb
    n = len(outline)
    start_row = vertex_w.get_write_row()
    for x, z, nx, nz in outline:
        for y in (-hd, hd):
            vertex_w.add_data3(x, y, z)
            normal_w.add_data3(nx, 0, nz)
            color_w.add_data4(r, g, b, alpha_for_z(z))

    # Ojo con el orden de los tres vértices: es lo que decide hacia dónde
    # mira la cara. Con (front_a, front_b, back_b) la normal geométrica del
    # lomo derecho sale en -X, o sea hacia DENTRO de la caja, y el backface
    # culling se lo lleva por delante: el lomo cercano no se dibujaba y solo
    # se veía el marco de la tapa frontal. En el reflejo sí se veía, porque
    # su `set_scale(1, 1, -1)` volvía a invertir el sentido y lo dejaba, por
    # casualidad, del derecho — de ahí el síntoma de "veo el lomo en el
    # reflejo pero no en la caja".
    for i in range(n):
        j = (i + 1) % n
        front_a, back_a = start_row + i * 2, start_row + i * 2 + 1
        front_b, back_b = start_row + j * 2, start_row + j * 2 + 1
        triangles.add_vertices(front_a, back_b, front_b)
        triangles.add_vertices(front_a, back_a, back_b)


def _build_case_body(
    width: float,
    height: float,
    depth: float,
    alpha_for_z: Callable[[float], float],
    body_color: tuple[float, float, float] = CASE_BODY_COLOR,
) -> GeomNode:
    """Estuche de esquinas redondeadas: tapa frontal, tapa trasera y banda lateral."""
    outline = _rounded_rect_outline(width, height, CORNER_RADIUS, CORNER_SEGMENTS)
    hd = depth / 2.0

    fmt = GeomVertexFormat.get_v3n3c4()
    vdata = GeomVertexData("case_body", fmt, Geom.UH_static)

    vertex_w = GeomVertexWriter(vdata, "vertex")
    normal_w = GeomVertexWriter(vdata, "normal")
    color_w = GeomVertexWriter(vdata, "color")
    triangles = GeomTriangles(Geom.UH_static)

    _add_cap(vertex_w, normal_w, color_w, triangles, outline, -hd, (0, -1, 0), body_color, alpha_for_z, reverse=False)
    _add_cap(vertex_w, normal_w, color_w, triangles, outline, hd, (0, 1, 0), body_color, alpha_for_z, reverse=True)
    _add_belt(vertex_w, normal_w, color_w, triangles, outline, hd, body_color, alpha_for_z)

    geom = Geom(vdata)
    geom.add_primitive(triangles)

    node = GeomNode("case_body")
    node.add_geom(geom)
    return node


def _flipped(node: GeomNode) -> GeomNode:
    """
    Invierte el sentido de giro de todos los triángulos de `node`.

    Lo necesita el reflejo: su `set_scale(1, 1, -1)` es una simetría, y
    una simetría invierte el sentido de giro de todo lo que cuelga de ella,
    con lo que el backface culling pasa a descartar justo las caras que
    deberían verse. Pre-invirtiendo la geometría, las dos inversiones se
    cancelan y el reflejo se dibuja con las mismas caras que la caja real.

    Las normales quedan apuntando al revés, pero da igual: el reflejo va con
    las luces apagadas (`set_light_off`) y no las usa.
    """
    for i in range(node.get_num_geoms()):
        node.modify_geom(i).reverse_in_place()
    return node


def inner_size(
    width: float = CASE_WIDTH, height: float = CASE_HEIGHT,
) -> tuple[float, float, float]:
    """
    Tamaño y radio de esquina del ÁREA INTERIOR del estuche: lo que queda
    dentro del marco, una vez metido `COVER_INSET` por cada lado. Dentro de
    ella van, sin solaparse, el banner arriba y la carátula debajo.

    Los tres valores se escalan por el MISMO factor: así el área interior
    mantiene la relación de aspecto del estuche y sus esquinas siguen siendo
    concéntricas con las de él (el marco tiene el mismo grosor en las
    curvas que en los tramos rectos).

    Es pública porque el banner de tiendas (`case_banner.py`) tiene que
    alinearse exactamente con esta área, no con el borde del estuche.
    """
    return width * _INSET_SCALE, height * _INSET_SCALE, CORNER_RADIUS * _INSET_SCALE


def cover_geometry(
    width: float = CASE_WIDTH, height: float = CASE_HEIGHT,
) -> tuple[float, float, float, float]:
    """
    `(ancho, alto, radio_inferior, z_centro)` de la carátula: el área
    interior menos la franja del banner, que queda por encima sin pisarla.

    El centro en z NO es 0 — la carátula está descentrada hacia abajo
    respecto al estuche, porque el banner le come la parte de arriba.
    """
    inner_w, inner_h, radius = inner_size(width, height)
    return inner_w, inner_h - BANNER_HEIGHT, radius, -BANNER_HEIGHT / 2.0


def _build_cover(
    width: float,
    height: float,
    radius: float,
    z_center: float,
    alpha_for_z: Callable[[float], float],
) -> GeomNode:
    """
    Carátula recortada al contorno del área interior: esquinas inferiores
    redondeadas igual que el estuche (si fueran rectas asomarían por fuera
    de su silueta curva) y esquinas superiores VIVAS, para quedar a ras del
    borde inferior recto del banner.

    Se construye ya en su z definitivo dentro del estuche (`z_center`), en
    vez de centrada en 0 y recolocada después: `alpha_for_z` espera
    coordenadas del ESTUCHE, y con la carátula descentrada las suyas
    propias ya no coinciden — el degradado del reflejo saldría desplazado.
    """
    outline = _rounded_rect_outline(width, height, radius, CORNER_SEGMENTS, top_radius=0.0)

    fmt = GeomVertexFormat.get_v3n3c4t2()
    vdata = GeomVertexData("cover", fmt, Geom.UH_static)

    vertex_w = GeomVertexWriter(vdata, "vertex")
    normal_w = GeomVertexWriter(vdata, "normal")
    color_w = GeomVertexWriter(vdata, "color")
    uv_w = GeomVertexWriter(vdata, "texcoord")
    triangles = GeomTriangles(Geom.UH_static)

    center_row = vertex_w.get_write_row()
    vertex_w.add_data3(0, 0, z_center)
    normal_w.add_data3(0, -1, 0)
    color_w.add_data4(1, 1, 1, alpha_for_z(z_center))
    uv_w.add_data2(0.5, 0.5)

    start_row = vertex_w.get_write_row()
    for x, z, _nx, _nz in outline:
        vertex_w.add_data3(x, 0, z_center + z)
        normal_w.add_data3(0, -1, 0)
        color_w.add_data4(1, 1, 1, alpha_for_z(z_center + z))
        # Mismo criterio de UV que usaba CardMaker (comprobado en runtime):
        # z=+h -> v=1, z=-h -> v=0. Se calcula con la z LOCAL de la
        # carátula (sin z_center), que es la que va de -alto/2 a +alto/2.
        uv_w.add_data2(x / width + 0.5, z / height + 0.5)

    n = len(outline)
    for i in range(n):
        a = start_row + i
        b = start_row + (i + 1) % n
        triangles.add_vertices(center_row, a, b)

    geom = Geom(vdata)
    geom.add_primitive(triangles)

    node = GeomNode("cover")
    node.add_geom(geom)
    return node


def build_game_case(
    parent: NodePath,
    width: float = CASE_WIDTH,
    height: float = CASE_HEIGHT,
    depth: float = CASE_DEPTH,
    body_color: tuple[float, float, float] = CASE_BODY_COLOR,
) -> tuple[NodePath, NodePath]:
    """
    Crea una caja de juego bajo `parent`.

    `body_color` es el color del ESTUCHE (tapas + banda lateral) — la
    carátula lleva su propia textura encima y no lo usa. Por defecto un
    navy neutro; en el carrusel real, `carousel.py` pasa el color de la
    tienda preferente del juego (ver `store_colors.py`), tanto para que se
    distinga qué tienda es de un vistazo como porque un color vivo se nota
    mucho más que un navy oscuro contra el fondo, también oscuro.

    Devuelve (case_np, cover_np): el nodo del estuche completo y el nodo de
    la carátula, para poder llamarle luego `cover_np.set_texture(...)`.
    """
    case_np = parent.attach_new_node(_build_case_body(width, height, depth, _OPAQUE, body_color))

    cover_np = case_np.attach_new_node(_build_cover(*cover_geometry(width, height), _OPAQUE))
    cover_np.set_pos(0, -depth / 2.0 - _COVER_OFFSET, 0)

    return case_np, cover_np


def build_case_reflection(
    parent: NodePath,
    width: float = CASE_WIDTH,
    height: float = CASE_HEIGHT,
    depth: float = CASE_DEPTH,
    max_alpha: float = 0.4,
    body_color: tuple[float, float, float] = CASE_BODY_COLOR,
) -> tuple[NodePath, NodePath]:
    """
    Reflejo de la caja ENTERA (estuche + carátula), no solo de la carátula:
    una copia en espejo bajo el estuche real, con desvanecimiento de alfa
    por vértice desde `max_alpha` (pegado al estuche) hasta 0 (al final del
    reflejo) — sin shader, Panda3D interpola el color entre vértices.

    Es un nodo hijo del propio estuche (no una instancia especular de toda
    la escena), reutilizando exactamente la misma geometría redondeada que
    `build_game_case`: se mueve, gira y se balancea con su caja
    automáticamente, y el plano de espejo es siempre el borde inferior LOCAL
    del estuche — nunca se desalinea aunque el carrusel entero se traslade.

    Devuelve (reflection_root, reflection_cover_np) para poder actualizar la
    textura reflejada cuando llega una descarga (`reflection_cover_np.set_texture`).
    """
    def alpha_for_z(z: float) -> float:
        # z=-height/2 (borde inferior real del estuche, el que tras el
        # espejo queda pegado a la caja) -> max_alpha.
        # z=+height/2 (borde superior, el que queda más lejos) -> 0.
        return max_alpha * (0.5 - z / height)

    root = parent.attach_new_node("case-reflection")
    root.set_scale(1, 1, -1)
    root.set_z(-height)
    root.set_transparency(TransparencyAttrib.M_alpha)
    root.set_light_off()

    # Geometría pre-invertida (ver `_flipped`) para compensar la simetría del
    # `set_scale(1, 1, -1)` de arriba. Sin esto el backface culling descarta
    # justo las caras que hay que ver: primero se lo llevó entera la carátula
    # reflejada — una tarjeta plana de una sola cara — dejando el síntoma de
    # "se refleja la caja pero no el cover"; el cuerpo se salvaba por ser un
    # sólido cerrado, donde ver las caras de detrás en vez de las de delante
    # es indistinguible al ser de color plano.
    root.attach_new_node(_flipped(_build_case_body(width, height, depth, alpha_for_z, body_color)))

    cover_np = root.attach_new_node(
        _flipped(_build_cover(*cover_geometry(width, height), alpha_for_z))
    )
    cover_np.set_pos(0, -depth / 2.0 - _COVER_OFFSET, 0)

    return root, cover_np


_PLACEHOLDER_CACHE: dict[tuple[float, float, float], Texture] = {}


def make_placeholder_texture(color: tuple[float, float, float]) -> Texture:
    """
    Textura 2x2 de un color sólido, usada como carátula de relleno mientras
    no hay arte real. `NearestFilter` evita que Panda3D intente suavizar un
    color plano de 2x2 con mipmaps.

    Se reutiliza la misma textura para el mismo color. Los colores salen de
    la paleta de tiendas, o sea que son cinco contados, y sin caché una
    biblioteca de 1266 juegos creaba 1266 texturas distintas —cada una con
    su hueco en la GPU— para pintar cinco colores planos.
    """
    cached = _PLACEHOLDER_CACHE.get(color)
    if cached is not None:
        return cached

    from panda3d.core import PNMImage

    image = PNMImage(2, 2)
    image.fill(*color)

    tex = Texture("placeholder_cover")
    tex.load(image)
    tex.set_minfilter(Texture.FT_nearest)
    tex.set_magfilter(Texture.FT_nearest)
    _PLACEHOLDER_CACHE[color] = tex
    return tex
