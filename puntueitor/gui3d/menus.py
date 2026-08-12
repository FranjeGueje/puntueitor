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

#: Mismo orden y mismas claves que la lista de la TUI.
SCORING_ITEMS = [
    MenuItem("mixed", "Mixed Score"),
    MenuItem("weighted", "Weighted Score"),
    MenuItem("time", "Available Time"),
    MenuItem("genre", "Genre Match"),
]

# ──────────────────────────────
# Filtrar y ordenar (X / x)
# ──────────────────────────────

FILTER_TITLE = "Filtrar y ordenar"

# Los dos grupos van en un solo menú, no en dos, porque en la práctica se
# tocan a la vez ("los terminados, por duración") y separarlos obligaría a
# entrar y salir dos veces. Los rótulos de sección no se pueden enfocar: al
# navegar se saltan solos (ver `Menu.move_focus`).
FILTER_ITEMS = [
    MenuItem("sec_sort", "ORDENAR POR", kind="header"),
    MenuItem("sort:title", "Nombre"),
    MenuItem("sort:user_score", "Puntuación de usuarios"),
    MenuItem("sort:critic_score", "Puntuación de crítica"),
    MenuItem("sort:mixed", "Puntuación media"),
    MenuItem("sort:duration", "Duración"),
    MenuItem("sec_filter", "FILTRAR", kind="header"),
    MenuItem("filter:finished:true", "Solo terminados"),
    MenuItem("filter:finished:false", "Solo no terminados"),
    MenuItem("filter:favorite:true", "Solo favoritos"),
    MenuItem("filter:backlog:true", "Solo backlog"),
    MenuItem("filter:hidden:true", "Solo ocultos"),
    MenuItem("filter:clear", "Limpiar filtros"),
]

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
