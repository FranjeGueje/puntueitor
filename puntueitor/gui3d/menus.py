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
    MenuItem("gui3d", "Puntueitor3D"),
    MenuItem("quit", "Salir"),
]

# ──────────────────────────────
# Puntueitor3D (Opciones -> Puntueitor3D)
# ──────────────────────────────

GUI3D_TITLE = "Puntueitor3D"

#: Cómo se llama de cara al usuario cada valor de `state.SCORE_SOURCES`.
SCORE_SOURCE_LABELS = {
    "steamdb": "SteamDB",
    "user": "Usuarios",
    "critic": "Crítica",
}

YES_NO_LABELS = {True: "Sí", False: "No"}


def build_gui3d_items(prefs) -> list[MenuItem]:
    """
    Los ajustes propios del frontend 3D, con los valores EN EDICIÓN.

    `prefs` es la copia que se está editando, no la que está en uso: como en
    el menú de Configuración y en los formularios de scoring, nada se aplica
    hasta pulsar "Guardar" (ver `app.App._open_gui3d_menu`).

    Los dos ajustes son `kind="cycle"`, el mismo tipo que los filtros de tres
    estados, así que heredan el cambio con izquierda/derecha sin tocar el
    widget de menú.
    """
    return [
        MenuItem(
            "set3d:score_source", "Puntuación mostrada", kind="cycle",
            value=SCORE_SOURCE_LABELS.get(prefs.score_source, prefs.score_source),
        ),
        MenuItem(
            # No dice "guardar" porque no es eso lo que decide: los filtros
            # se guardan al aplicarlos, y esto elige si se recuperan en el
            # siguiente arranque.
            "set3d:remember_filters", "Cargar filtros al inicio", kind="cycle",
            value=YES_NO_LABELS[bool(prefs.remember_filters)],
        ),
        MenuItem("sec3d_end", "", kind="header"),
        MenuItem("set3d:save", "Guardar"),
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
# Configuración (Opciones -> Configuración)
# ──────────────────────────────

SETTINGS_TITLE = "Configuración"

#: Con qué se tapan las credenciales en la lista. Ni la clave de Steam ni el
#: secreto de IGDB se enseñan al navegar el menú; sí al editarlos, porque
#: una clave que no se ve no se puede corregir si te equivocas en un
#: carácter, y para entonces ya has entrado a propósito a cambiarla.
SECRET_MASK = "••••••••"

#: Las cuatro tiendas, con el campo de `Config` que las activa.
SETTINGS_STORES = (
    ("steam_is_active", "Steam"),
    ("gog_is_active", "GOG"),
    ("epic_is_active", "Epic"),
    ("amazon_is_active", "Amazon"),
)

#: Campos de texto: clave de config, etiqueta y si va tapado en la lista.
SETTINGS_TEXTS = (
    ("igdb_client_id", "Client ID", False),
    ("igdb_client_secret", "Client Secret", True),
    ("steam_user_id", "Steam User ID", False),
    ("steam_api_key", "API Key", True),
)


def _shown(value: str, secret: bool) -> str:
    if not value:
        return "N/A"
    return SECRET_MASK if secret else value


def build_settings_items(values: dict) -> list[MenuItem]:
    """
    El menú de configuración, con los mismos campos que la pantalla de la
    TUI (`gui/screens/configuration.py`) y en el mismo orden.

    `values` son los valores EN EDICIÓN, no los guardados: como en el resto
    de formularios, se trabaja sobre una copia y solo se escribe al dar a
    "Guardar" (ver `app.App._open_settings_menu`).
    """
    items = [MenuItem("sec_igdb", "IGDB", kind="header")]
    items += [
        MenuItem(
            f"set:{key}", label,
            value=_shown(str(values.get(key) or ""), secret),
            payload={"field": key, "secret": secret},
        )
        for key, label, secret in SETTINGS_TEXTS[:2]
    ]

    items.append(MenuItem("sec_steam", "STEAM", kind="header"))
    items += [
        MenuItem(
            f"set:{key}", label,
            value=_shown(str(values.get(key) or ""), secret),
            payload={"field": key, "secret": secret},
        )
        for key, label, secret in SETTINGS_TEXTS[2:]
    ]

    items.append(MenuItem("sec_stores", "TIENDAS A CARGAR", kind="header"))
    items += [
        MenuItem(
            f"set:{field}", label, kind="check",
            checked=bool(values.get(field)),
            payload={"field": field},
        )
        for field, label in SETTINGS_STORES
    ]

    items.append(MenuItem("sec_heroic", "CARPETA DE HEROIC O RELIC", kind="header"))
    items.append(MenuItem(
        "set:heroic_path", "Carpeta",
        # Vacío significa "búscala tú", no "sin poner"; se dice así en vez de
        # con un N/A, que aquí se leería como un error.
        value=values.get("heroic_path") or "auto",
        payload={"field": "heroic_path", "secret": False},
    ))

    items.append(MenuItem("sec_end", "", kind="header"))
    items.append(MenuItem("set:save", "Guardar"))
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
    ("backlog", "Pendiente de jugar"),
    ("favorite", "Favorito"),
)

#: Las dos acciones de "AVANZADO". Van separadas de las casillas porque no
#: son un estado que se marca y se desmarca: una tarda (va a la red) y la
#: otra saca el juego de la biblioteca, así que las dos preguntan antes.
ENRICH_KEY = "game:enrich"
FORGET_KEY = "game:forget"

ENRICH_QUESTION = (
    "¿Seguro que quieres buscar",
    "información extra para este juego?",
)
ENRICH_YES = "Sí, enriquecer"

FORGET_QUESTION = (
    "¿Seguro que quieres olvidar este juego",
    "y moverlo a desconocidos?",
)
FORGET_YES = "Sí, desconocer"


def build_game_items(game: Game) -> list[MenuItem]:
    """
    El menú de un juego: sus estados y las acciones avanzadas.

    Se reconstruye cada vez que se abre en vez de crearlo una vez y
    actualizarlo: el menú se abre sobre un juego distinto cada vez, y
    arrastrar las casillas del anterior es justo el fallo que haría marcar
    como terminado al juego equivocado.
    """
    items = [MenuItem("sec_flags", "ESTADOS", kind="header")]
    items += [
        MenuItem(
            key=f"flag:{field}",
            label=label,
            kind="check",
            checked=bool(getattr(game, field)),
            payload={"field": field},
        )
        for field, label in GAME_FLAGS
    ]
    items += [
        MenuItem("sec_advanced", "AVANZADO", kind="header"),
        MenuItem(ENRICH_KEY, "Enriquecer"),
        MenuItem(FORGET_KEY, "Desconocer"),
    ]
    return items


# ──────────────────────────────
# Juegos desconocidos (arriba sobre el carrusel)
# ──────────────────────────────

UNKNOWN_TITLE_KEY = "unk:title"
UNKNOWN_STORE_KEY = "unk:store"

#: Prefijo de las filas de resultados de IGDB. El id va en el `payload`, no
#: en la clave: la clave solo tiene que ser única dentro del menú.
UNKNOWN_RESULT_PREFIX = "unkres:"

UNKNOWN_RESULTS_TITLE = "Resultados de IGDB"


def build_unknown_items(unknown) -> list[MenuItem]:
    """
    Las dos formas de identificar un juego desconocido, las mismas que la
    TUI (`tui/screens/unknown_menu.py`) y en el mismo orden.

    "Volver" no está: se sale con B, como en todos los menús de aquí.
    """
    return [
        MenuItem(UNKNOWN_TITLE_KEY, "Buscar por título"),
        MenuItem(UNKNOWN_STORE_KEY, "Volver a buscar por tienda"),
    ]


def build_search_result_items(results) -> list[MenuItem]:
    """
    Un elemento por resultado de IGDB.

    El año va en la columna de la derecha (`value`) y no pegado al título:
    con quince resultados de nombres casi iguales —remasterizaciones,
    ediciones de oro, la trilogía— el año alineado es lo que deja
    distinguirlos de un vistazo.
    """
    return [
        MenuItem(
            f"{UNKNOWN_RESULT_PREFIX}{result.igdb_id}",
            result.title,
            value=str(result.year) if result.year else "—",
            payload={"result": result},
        )
        for result in results
    ]


# ──────────────────────────────
# Confirmación (¿seguro?)
# ──────────────────────────────

CONFIRM_NO_KEY = "confirm_no"
CONFIRM_YES_KEY = "confirm_yes"


def build_confirm_items(
    question_lines: tuple[str, ...],
    yes_label: str,
    no_label: str = "No, cancelar",
) -> list[MenuItem]:
    """
    Las filas de una confirmación: la pregunta y las dos salidas.

    La pregunta va como rótulos de sección, UNO POR LÍNEA: un rótulo no
    admite saltos de línea (su alto está fijado en `HEADER_HEIGHT` y dos
    líneas se solaparían con la fila siguiente).

    Y va aquí y no en el título del menú porque no cabe: el título se dibuja
    a `TITLE_SCALE`, y una frase entera pide más ancho del que permite
    `PANEL_MAX_HALF_WIDTH`. El título lleva el nombre del juego, que es lo
    que hace falta para saber sobre qué se está confirmando.

    El "No" va primero a propósito, como en el menú de salir: `set_items`
    deja el foco en la primera fila enfocable, así que la opción que viene
    marcada de serie es la que no hace nada.
    """
    items = [
        MenuItem(f"confirm_q{index}", line, kind="header")
        for index, line in enumerate(question_lines)
    ]
    items += [
        MenuItem("confirm_sep", "", kind="header"),
        MenuItem(CONFIRM_NO_KEY, no_label),
        MenuItem(CONFIRM_YES_KEY, yes_label),
    ]
    return items
