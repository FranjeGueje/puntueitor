"""
Rectángulo de esquinas redondeadas para los paneles de la interfaz 2D.

Panda3D no trae ninguno: `DirectFrame` con `relief=FLAT` dibuja un
rectángulo en pico, y su relieve `RIDGE`/`GROOVE` añade bisel pero sigue
teniendo las esquinas en ángulo recto. La alternativa habitual es una
textura de nueve trozos ("9-slice"), pero eso pide un PNG por color de
panel; generando la geometría se puede pedir cualquier color y cualquier
radio sin añadir ningún asset.

Vive aparte de `menu.py` porque no tiene nada que ver con menús — es una
primitiva de dibujo, y el fondo de la ficha (`app.py`) puede querer la misma
forma más adelante.
"""
from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
)

#: Segmentos por esquina. Ocho ya no se distingue de una curva perfecta al
#: tamaño de un panel en pantalla, y son solo 32 triángulos por panel.
CORNER_SEGMENTS = 8


def _corner_points(
    left: float, right: float, bottom: float, top: float,
    radius: float, segments: int,
) -> list[tuple[float, float]]:
    """
    Contorno del rectángulo redondeado, en orden antihorario.

    El radio se recorta a la mitad del lado más corto: pedir un radio mayor
    que eso no tiene solución (las curvas de dos esquinas se solaparían) y
    lo razonable es dar la forma de píldora en vez de reventar.
    """
    import math

    radius = min(radius, (right - left) / 2.0, (top - bottom) / 2.0)

    # Centro de la curva de cada esquina y ángulo en el que empieza, dando
    # la vuelta en sentido antihorario desde la esquina inferior derecha.
    corners = (
        (right - radius, bottom + radius, -90.0),
        (right - radius, top - radius, 0.0),
        (left + radius, top - radius, 90.0),
        (left + radius, bottom + radius, 180.0),
    )

    points: list[tuple[float, float]] = []
    for cx, cz, start in corners:
        for i in range(segments + 1):
            angle = math.radians(start + 90.0 * i / segments)
            points.append((cx + radius * math.cos(angle), cz + radius * math.sin(angle)))
    return points


def make_rounded_panel(
    parent: NodePath,
    left: float, right: float, bottom: float, top: float,
    radius: float,
    color: tuple[float, float, float, float],
    segments: int = CORNER_SEGMENTS,
) -> NodePath:
    """
    Crea un panel redondeado bajo `parent` y devuelve su nodo.

    Se dibuja como un abanico de triángulos desde el centro hasta el
    contorno, que para una forma convexa como esta es válido siempre y evita
    tener que triangular nada.

    El color va en los vértices, no en un `set_color()` sobre el nodo, para
    que el panel se pueda teñir después con `set_color_scale()` (fundidos de
    entrada/salida) sin perder el color base.
    """
    points = _corner_points(left, right, bottom, top, radius, segments)

    vformat = GeomVertexFormat.get_v3c4()
    vdata = GeomVertexData("rounded-panel", vformat, Geom.UH_static)
    vdata.set_num_rows(len(points) + 1)

    vertex = GeomVertexWriter(vdata, "vertex")
    color_writer = GeomVertexWriter(vdata, "color")

    # El centro es el vértice 0; el contorno, del 1 en adelante.
    vertex.add_data3((left + right) / 2.0, 0.0, (bottom + top) / 2.0)
    color_writer.add_data4(*color)
    for x, z in points:
        vertex.add_data3(x, 0.0, z)
        color_writer.add_data4(*color)

    triangles = GeomTriangles(Geom.UH_static)
    count = len(points)
    for i in range(count):
        # El último triángulo cierra contra el primer punto del contorno, de
        # ahí el módulo — si no, quedaría una muesca en la esquina inferior
        # derecha, justo donde empieza y acaba el recorrido.
        triangles.add_vertices(0, i + 1, (i + 1) % count + 1)

    geom = Geom(vdata)
    geom.add_primitive(triangles)
    node = GeomNode("rounded-panel")
    node.add_geom(geom)

    panel = parent.attach_new_node(node)
    panel.set_transparency(True)
    # Sin esto el panel se sombrearía con las luces de la escena 3D si
    # alguien lo cuelga de `render` en vez de `aspect2d`.
    panel.set_light_off()
    return panel
