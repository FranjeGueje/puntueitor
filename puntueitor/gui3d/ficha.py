"""
Ficha del juego seleccionado: los mismos datos que enseña la TUI en
`gui/widgets/game_detail.py`, formateados igual, menos la URL de la
carátula (en la TUI es un enlace en el que se puede pinchar; aquí no
serviría de nada, y además la carátula ya se está viendo en grande).

Este módulo solo da texto. Quién lo coloca en pantalla, con qué tamaños y
en cuántas columnas, es cosa de `app.py`.

Sin emoji en las etiquetas, al revés que la TUI: la fuente por defecto de
Panda3D no trae esos glifos y salen como cuadros vacíos (comprobado
renderizando; avisa por consola con "No definition in for character
U+1f3ae" y similares). Las tildes y la eñe sí las trae, así que el texto va
acentuado con normalidad.
"""
from puntueitor.core.models import Game

# Copiado de `gui/widgets/game_detail.py`. No se importa de allí para no
# arrastrar Textual —y con él toda la TUI— dentro del frontend 3D solo por
# una tabla de diez cadenas. Son las categorías fijas de reseñas de Steam;
# si algún día cambian, hay que tocar los dos sitios.
REVIEW_LABELS = {
    0: "Sin análisis de usuarios",
    1: "Extremadamente negativas",
    2: "Muy negativas",
    3: "Negativas",
    4: "Mayormente negativas",
    5: "Variadas",
    6: "Mayormente positivas",
    7: "Positivas",
    8: "Muy positivas",
    9: "Extremadamente positivas",
}

NOT_AVAILABLE = "N/A"
FALLBACK_DESCRIPTION = "Sin descripción disponible."

STEAMDB_NOTE = "*Fórmula avanzada en base a puntuaciones de Steam"


def _thousands(value: int) -> str:
    """1234567 -> '1.234.567' (separador de miles español)."""
    return f"{value:,}".replace(",", ".")


def _steam_review(game: Game) -> str:
    label = REVIEW_LABELS.get(game.steam_review, NOT_AVAILABLE)
    if game.review_pos is None or game.review_neg is None:
        return label
    total = game.review_pos + game.review_neg
    return f"{label} ({_thousands(game.review_pos)} positivas de {_thousands(total)} totales)"


# Etiquetas fijas, en el orden en que se muestran. Van aparte de los valores
# porque no cambian nunca: quien dibuja la ficha crea una fila por etiqueta
# una sola vez y luego solo refresca la columna de valores al navegar.
FIELD_LABELS: tuple[str, ...] = (
    "Géneros",
    "Duración",
    "Puntuación Usuario",
    "Puntuación Crítica",
    "Puntuación SteamDB",
    "Puntuación Steam",
    "Tiendas",
    "Lanzamiento",
)


def build_values(game: Game) -> list[str]:
    """Valores de la ficha, en el mismo orden que `FIELD_LABELS`."""
    genres = ", ".join(game.genres) if game.genres else "Desconocido"

    # El >0 no sobra: un juego enriquecido con 0 horas es "sin dato", no un
    # juego que se pase en cero horas. Mismo criterio que la TUI.
    duration = (
        f"{game.duration_hours}h"
        if game.duration_hours is not None and game.duration_hours > 0
        else NOT_AVAILABLE
    )
    user_score = f"{game.user_score:.0f}/100" if game.user_score is not None else NOT_AVAILABLE
    critic_score = f"{game.critic_score:.0f}/100" if game.critic_score is not None else NOT_AVAILABLE
    steamdb = f"{game.steamdb_score:.2f}" if game.steamdb_score is not None else NOT_AVAILABLE
    stores = ", ".join(game.stores.keys()) if game.stores else "Ninguna"
    release = game.release_date.strftime("%d/%m/%Y") if game.release_date else NOT_AVAILABLE

    values = [
        genres,
        duration,
        user_score,
        critic_score,
        f"{steamdb}   {STEAMDB_NOTE}",
        _steam_review(game),
        stores,
        release,
    ]
    assert len(values) == len(FIELD_LABELS), "valores y etiquetas descuadrados"
    return values


# La sinopsis de IGDB no tiene límite de longitud y la ficha sí: medido
# sobre la biblioteca real, la más larga ocupaba 107 líneas, unas nueve
# veces el alto disponible. La TUI se permite no recortar porque su panel
# tiene scroll; aquí no lo hay, así que se corta por la última palabra
# entera que quepa.
MAX_DESCRIPTION_CHARS = 480


def build_description(game: Game) -> str:
    if not game.storyline:
        return FALLBACK_DESCRIPTION
    if len(game.storyline) <= MAX_DESCRIPTION_CHARS:
        return game.storyline
    return f"{game.storyline[:MAX_DESCRIPTION_CHARS].rsplit(' ', 1)[0]}..."
