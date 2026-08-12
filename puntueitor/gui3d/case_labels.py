"""
Etiquetas ("pegatinas") sobre el frontal de la caja: favorito, terminado,
backlog, puntuación y duración. Van SIEMPRE en el frontal de la caja —
delante de la carátula y del banner de tiendas, como un post-it pegado
encima de una caja real — y solo en la caja de verdad, nunca en su reflejo
(el reflejo solo espeja estuche + carátula, ver
`game_case.build_case_reflection`; el banner de tiendas tampoco se refleja,
mismo criterio).

Cuatro huecos fijos, no configurables por juego:

    favorito              arriba-izquierda
    terminado / backlog   arriba-derecha    (ver abajo)
    duración              abajo-centro      número pintado encima
    puntuación            abajo-derecha     número pintado encima

Terminado y backlog comparten la columna de arriba-derecha. Si el juego solo
tiene uno de los dos, va en la posición de siempre. Si tiene los DOS a la
vez, "terminado" se queda arriba (donde siempre) y "backlog" se pinta justo
debajo, en la misma vertical — así se ven ambas etiquetas sin que ninguna
tape a la otra ni haga falta elegir cuál prevalece.

Cada etiqueta solo aparece si su dato está presente: favorito, terminado y
backlog son `True`, puntuación y duración tienen un valor real. Un juego
recién añadido y sin enriquecer no debería salir con una pegatina de "N/A"
pegada encima — eso sería ruido, no información.

Todas se pueden ocultar de golpe (tecla espacio / botón Y del mando, ver
`app.App._toggle_labels`), para poder ver la carátula sin nada encima.
"""
from pathlib import Path

from panda3d.core import (
    CardMaker,
    Filename,
    NodePath,
    TextNode,
    Texture,
    TexturePool,
    TransparencyAttrib,
)

from puntueitor.core.models import Game
from puntueitor.gui3d.fonts import ui_font
from puntueitor.gui3d.game_case import CASE_DEPTH, CASE_HEIGHT, CASE_WIDTH

_ASSETS_DIR = Path(__file__).parent / "assets" / "labels"

# Favorito/terminado: "pegatina" notablemente más grande que la franja del
# banner (0.11) — se pidió expresamente que asomaran por encima y por
# debajo de su nivel, no que quedaran encajadas dentro. TOP_MARGIN es la
# distancia entre el borde superior de la pegatina y el borde superior del
# estuche: sin margen, quedaría exactamente a ras del canto del estuche, que
# se ve como si la pegatina "flotase" cortada en seco contra el fondo; un
# margen pequeño la deja asomando de forma natural, apoyada en la esquina.
TOP_LABEL_SIZE = 0.22
TOP_LABEL_TOP_MARGIN = 0.01
TOP_LABEL_SIDE_MARGIN = 0.02

# Cuando un juego es terminado Y backlog a la vez, la segunda etiqueta
# (backlog) se apila justo debajo de la primera (terminado), en la misma
# columna. El hueco entre las dos es más pequeño que el margen superior:
# aquí las separa una etiqueta de la otra, no una etiqueta del canto de la
# caja, así que no hace falta el mismo respiro.
TOP_LABEL_STACK_GAP = 0.015

# Duración y puntuación. Ya no son tres en la franja de abajo (backlog se
# fue arriba, al hueco de terminado), así que sobra sitio y pueden ir más
# grandes — que además es lo que interesa, porque son las únicas que llevan
# un número dentro que hay que poder leer a la distancia del carrusel.
BOTTOM_LABEL_SIZE = 0.27
BOTTOM_LABEL_BOTTOM_MARGIN = 0.015
BOTTOM_LABEL_SIDE_MARGIN = 0.03

# Y locales (delante = más negativo): la carátula está en -depth/2-0.002 y
# el banner en -depth/2-0.004 (ver `game_case.py`/`case_banner.py`). Las
# pegatinas van por delante de las dos, si no el banner las taparía en las
# esquinas superiores.
_LABEL_ICON_Y = -CASE_DEPTH / 2 - 0.007
_LABEL_TEXT_Y = -CASE_DEPTH / 2 - 0.009

# Tamaño del número y su posición dentro del icono, los dos como FRACCIÓN
# del tamaño del icono en vez de en unidades absolutas: así, al reescalar la
# pegatina, el número y su encaje se reescalan solos y no hay que recalibrar
# cuatro constantes a mano cada vez.
#
# Ninguno de los dos números va centrado del todo: la estrella tiene las dos
# puntas de abajo, así que su zona ancha está por encima del centro
# geométrico y el número pide bajar un poco para verse ópticamente centrado;
# el reloj tiene la esfera clara algo descentrada en su lienzo de 512x512.
# Ajustado sobre el render, que es lo único que vale aquí — el centro
# geométrico del PNG no es el centro visual de un icono con esa forma.
_SCORE_TEXT_SCALE = BOTTOM_LABEL_SIZE * 0.30
_DURATION_TEXT_SCALE = BOTTOM_LABEL_SIZE * 0.32
_LABEL_TEXT_COLOR = (0.05, 0.05, 0.05, 1)

_SCORE_TEXT_OFFSET = (0.0, -BOTTOM_LABEL_SIZE * 0.075)
_DURATION_TEXT_OFFSET = (0.0, -BOTTOM_LABEL_SIZE * 0.05)

_texture_cache: dict[str, Texture] = {}


def _load_label_texture(name: str) -> Texture:
    """Textura de un icono de etiqueta, cacheada — son solo cinco y estáticos."""
    cached = _texture_cache.get(name)
    if cached is not None:
        return cached

    path = _ASSETS_DIR / f"{name}.png"
    texture = TexturePool.load_texture(Filename.from_os_specific(str(path)))
    if texture is not None:
        texture.set_minfilter(Texture.FT_linear_mipmap_linear)
        texture.set_magfilter(Texture.FT_linear)
        texture.set_anisotropic_degree(16)
        _texture_cache[name] = texture
    return texture


def _build_icon(parent: NodePath, name: str, size: float, x: float, z: float) -> NodePath:
    card = CardMaker(f"label-{name}")
    card.set_frame(-size / 2, size / 2, -size / 2, size / 2)
    node = parent.attach_new_node(card.generate())
    node.set_texture(_load_label_texture(name))
    node.set_transparency(TransparencyAttrib.M_alpha)
    node.set_light_off()
    node.set_pos(x, _LABEL_ICON_Y, z)
    return node


# Cuánto se encoge el número cuando tiene tres cifras. El icono es redondo
# y el hueco útil no da para tres dígitos al tamaño de dos: en la biblioteca
# real hay 7 juegos que pasan de 100 horas (el más largo, 169) y la
# puntuación puede llegar a 100. Encogiendo solo esos casos, el número se ve
# grande en el 99% de las cajas sin que el 1% restante se salga del icono.
_THREE_DIGIT_SCALE = 0.75


def _build_number(
    parent: NodePath, name: str, text: str, scale: float,
    x: float, z: float, offset: tuple[float, float],
) -> None:
    if len(text) >= 3:
        scale *= _THREE_DIGIT_SCALE

    node = TextNode(f"label-text-{name}")
    node.set_text(text)
    node.set_align(TextNode.A_center)
    node.set_text_color(*_LABEL_TEXT_COLOR)
    font = ui_font()
    if font is not None:
        node.set_font(font)
    label_np = parent.attach_new_node(node)
    label_np.set_light_off()
    label_np.set_scale(scale)
    ox, oz = offset
    label_np.set_pos(x + ox, _LABEL_TEXT_Y, z + oz - scale * 0.32)


def build_case_labels(parent: NodePath, game: Game | None) -> NodePath | None:
    """
    Construye las etiquetas de estado de una caja. Devuelve None (sin crear
    nada) si no hay ficha del juego — pasa con `sample_data`/`real_data`
    incompletos, aunque en la práctica ambos rellenan `game` siempre.
    """
    if game is None:
        return None

    root = parent.attach_new_node("case-labels")

    hw = CASE_WIDTH / 2
    hh = CASE_HEIGHT / 2

    top_x = hw - TOP_LABEL_SIDE_MARGIN - TOP_LABEL_SIZE / 2
    top_z = hh - TOP_LABEL_TOP_MARGIN - TOP_LABEL_SIZE / 2

    bottom_x = hw - BOTTOM_LABEL_SIDE_MARGIN - BOTTOM_LABEL_SIZE / 2
    bottom_z = -hh + BOTTOM_LABEL_BOTTOM_MARGIN + BOTTOM_LABEL_SIZE / 2

    if game.favorite:
        _build_icon(root, "favorite", TOP_LABEL_SIZE, -top_x, top_z)

    # Misma columna para los dos. Si el juego tiene los dos estados a la vez,
    # "terminado" se queda en su sitio de siempre y "backlog" se apila justo
    # debajo, en la misma vertical, en vez de tener que elegir cuál de las
    # dos se pierde.
    if game.finished:
        _build_icon(root, "finish", TOP_LABEL_SIZE, top_x, top_z)
        if game.backlog:
            stacked_z = top_z - TOP_LABEL_SIZE - TOP_LABEL_STACK_GAP
            _build_icon(root, "backlog", TOP_LABEL_SIZE, top_x, stacked_z)
    elif game.backlog:
        _build_icon(root, "backlog", TOP_LABEL_SIZE, top_x, top_z)

    # Por defecto SteamDB — pendiente de que el menú de opciones permita
    # elegir usuario/crítica/SteamDB (ver conversación de diseño). Cuando
    # exista ese ajuste, este valor deja de ser un literal fijo.
    score = game.steamdb_score
    if score is not None:
        _build_icon(root, "score", BOTTOM_LABEL_SIZE, bottom_x, bottom_z)
        _build_number(
            root, "score", f"{score:.0f}", _SCORE_TEXT_SCALE,
            bottom_x, bottom_z, _SCORE_TEXT_OFFSET,
        )

    # El mismo criterio que la ficha (`ficha.py`): 0 horas es "sin dato",
    # no un juego que se completa instantáneamente.
    if game.duration_hours is not None and game.duration_hours > 0:
        _build_icon(root, "clock", BOTTOM_LABEL_SIZE, 0.0, bottom_z)
        _build_number(
            root, "clock", f"{game.duration_hours:.0f}", _DURATION_TEXT_SCALE,
            0.0, bottom_z, _DURATION_TEXT_OFFSET,
        )

    return root
