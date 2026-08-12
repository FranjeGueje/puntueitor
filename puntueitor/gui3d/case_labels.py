"""
Etiquetas ("pegatinas") sobre el frontal de la caja: favorito, terminado,
backlog, puntuación y duración. Van SIEMPRE en el frontal de la caja —
delante de la carátula y del banner de tiendas, como un post-it pegado
encima de una caja real — y solo en la caja de verdad, nunca en su reflejo
(el reflejo solo espeja estuche + carátula, ver
`game_case.build_case_reflection`; el banner de tiendas tampoco se refleja,
mismo criterio).

Cinco posiciones fijas, no configurables por juego:

    favorito     arriba-izquierda   pegatina grande, nivel del banner
    terminado    arriba-derecha     pegatina grande, nivel del banner
    backlog      abajo-izquierda    pegatina pequeña
    puntuación   abajo-derecha      pegatina pequeña, número pintado encima
    duración     abajo-centro       pegatina pequeña, número pintado encima

Cada una solo aparece si el dato correspondiente está presente: favorito,
terminado y backlog son `True`, puntuación y duración tienen un valor real.
Un juego recién añadido y sin enriquecer no debería salir con una pegatina
de "N/A" pegada encima — eso sería ruido, no información.
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

# Backlog/puntuación/duración: mismo tamaño entre sí (pedido explícito),
# más pequeñas que las de arriba porque son TRES en la misma franja inferior
# y tienen que caber sin tocarse.
BOTTOM_LABEL_SIZE = 0.16
BOTTOM_LABEL_BOTTOM_MARGIN = 0.015
BOTTOM_LABEL_SIDE_MARGIN = 0.03

# Y locales (delante = más negativo): la carátula está en -depth/2-0.002 y
# el banner en -depth/2-0.004 (ver `game_case.py`/`case_banner.py`). Las
# pegatinas van por delante de las dos, si no el banner las taparía en las
# esquinas superiores.
_LABEL_ICON_Y = -CASE_DEPTH / 2 - 0.007
_LABEL_TEXT_Y = -CASE_DEPTH / 2 - 0.009

_SCORE_TEXT_SCALE = 0.032
_DURATION_TEXT_SCALE = 0.032
_LABEL_TEXT_COLOR = (0.05, 0.05, 0.05, 1)

# Centro de la cara "en blanco" de cada icono donde pintar el número, en
# fracción del tamaño del icono desde su propio centro (0,0 = centro exacto).
# El reloj no está perfectamente centrado en el lienzo de 512x512 (la esfera
# clara queda un poco por debajo del centro geométrico) — medido a ojo sobre
# el PNG, no hay forma de calcularlo del contorno.
_SCORE_TEXT_OFFSET = (0.0, 0.0)
_DURATION_TEXT_OFFSET = (0.0, -0.008)

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


def _build_number(
    parent: NodePath, name: str, text: str, scale: float,
    x: float, z: float, offset: tuple[float, float],
) -> None:
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
    if game.finished:
        _build_icon(root, "finish", TOP_LABEL_SIZE, top_x, top_z)
    if game.backlog:
        _build_icon(root, "backlog", BOTTOM_LABEL_SIZE, -bottom_x, bottom_z)

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
