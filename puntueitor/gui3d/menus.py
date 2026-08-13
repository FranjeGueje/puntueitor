"""
Contenido de los menús: qué elementos lleva cada uno y qué clave devuelve.

Separado de `menu.py` (que es el widget, sin saber de juegos ni de scoring) y
de `app.py` (que es quien los abre y reacciona). Así se puede cambiar el
texto o el orden de un menú sin tocar ni el dibujo ni la lógica de entrada.

Las claves (`MenuItem.key`) son el contrato con `app.py`: son las que llegan
al manejador cuando se elige un elemento, y coinciden a propósito con las que
usa la TUI (`gui/screens/scoring.py`, `sorting.py`, `filtering.py`) para que
las dos interfaces hablen el mismo idioma cuando se conecten a la lógica de
verdad.
"""
from puntueitor.core.models import Game
from puntueitor.gui3d import scoring_info
from puntueitor.gui3d.menu import MenuItem

# ──────────────────────────────
# Opciones (Select / Esc)
# ──────────────────────────────

OPTIONS_TITLE = "Opciones"
OPTIONS_ITEMS = [
    MenuItem("config", "Configuración"),
    MenuItem("quit", "Salir"),
]

# ──────────────────────────────
# Salir (confirmación)
# ──────────────────────────────

QUIT_TITLE = "¿Salir de Puntueitor?"
QUIT_ITEMS = [
    MenuItem("quit_no", "No, seguir aquí"),
    MenuItem("quit_yes", "Sí, salir"),
]

# ──────────────────────────────
# Puntueitor: sistemas de scoring (Start / Tab)
# ──────────────────────────────

SCORING_TITLE = "Puntueitor - Sistemas de Scoring"


def build_scoring_items() -> list[MenuItem]:
    """Un elemento por sistema de scoring, en el orden de la TUI."""
    return [
        MenuItem(scorer.key, scorer.name) for scorer in scoring_info.SCORERS
    ]

# ──────────────────────────────
# Filtrar y ordenar (X / x)
# ──────────────────────────────

FILTER_TITLE = "Filtrar y ordenar"

#: Los tres filtros de estado, con el campo de `Game` al que corresponden.
#: Rotan entre N/A, Sí y No con izquierda/derecha (ver `filters.py`).
FILTER_TRISTATES = (
    ("finished", "Terminados"),
    ("favorite", "Favoritos"),
    ("backlog", "Backlog"),
)


def build_filter_items(filters, tristate_label) -> list[MenuItem]:
    """
    El menú de filtrar y ordenar, con los valores que tienen los filtros
    ahora mismo.

    Se reconstruye al abrirlo en vez de crearse una vez porque los valores
    se ven en las propias etiquetas ("Nombre <hollow>"), y un menú creado al
    arrancar los enseñaría siempre vacíos.

    Los dos grupos —ordenar y filtrar— van en un solo menú, no en dos,
    porque en la práctica se tocan a la vez ("los terminados, por duración")
    y separarlos obligaría a entrar y salir dos veces. Los rótulos de
    sección no se pueden enfocar: al navegar se saltan solos (ver
    `Menu.move_focus`).
    """
    items = [
        MenuItem("sec_sort", "ORDENAR POR", kind="header"),
        MenuItem("sort:title", "Nombre"),
        MenuItem("sort:user_score", "Puntuación de usuarios"),
        MenuItem("sort:critic_score", "Puntuación de crítica"),
        MenuItem("sort:steamdb", "Puntuación de SteamDB"),
        MenuItem("sort:duration", "Duración"),
        MenuItem("sec_filter", "FILTRAR", kind="header"),
        MenuItem("filter:name", "Nombre", value=filters.name or "N/A"),
        MenuItem(
            "filter:duration", "Duración máx.",
            value=f"{filters.max_duration:g} h" if filters.max_duration else "N/A",
        ),
    ]
    items += [
        MenuItem(
            f"filter:{field}", label, kind="cycle",
            value=tristate_label(getattr(filters, field)),
            payload={"field": field},
        )
        for field, label in FILTER_TRISTATES
    ]
    items += [
        MenuItem("sec_apply", "", kind="header"),
        MenuItem("filter:apply", "Aplicar filtros"),
        MenuItem("filter:clear", "Limpiar filtros"),
    ]
    return items

# ──────────────────────────────
# Juego (A sobre el carrusel)
# ──────────────────────────────

#: Casilla -> campo de `Game` que marca. El orden es el de la TUI
#: (`gui/screens/game_options.py`), para que quien use las dos interfaces
#: encuentre las mismas cosas en el mismo sitio.
GAME_FLAGS = (
    ("finished", "Terminado"),
    ("hidden", "Oculto"),
    ("backlog", "Pendiente (Backlog)"),
    ("favorite", "Favorito"),
)


def build_game_items(game: Game) -> list[MenuItem]:
    """
    Las casillas del menú de un juego, con el estado que tiene ahora.

    Se reconstruyen cada vez que se abre el menú en vez de crearlas una vez
    y actualizarlas: el menú se abre sobre un juego distinto cada vez, y
    arrastrar las casillas del anterior es justo el fallo que haría marcar
    como terminado al juego equivocado.
    """
    return [
        MenuItem(
            key=f"flag:{field}",
            label=label,
            kind="check",
            checked=bool(getattr(game, field)),
            payload={"field": field},
        )
        for field, label in GAME_FLAGS
    ]
