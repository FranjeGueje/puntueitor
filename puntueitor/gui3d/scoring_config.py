"""
Configuración de cada sistema de scoring, equivalente a la pantalla
`gui/screens/scoring_config.py` de la TUI.

Tres formularios, según el sistema:

    weights   tres porcentajes (críticos, usuarios, duración) que deben
              sumar 100 — para Mixed y Weighted
    hours     las horas disponibles — para Available Time
    genres    los géneros preferidos, marcables — para Genre Match

Los valores viven en `scoring.json` (`paths.scoring_file()`), el MISMO que
lee y escribe la TUI, así que lo que se cambie aquí se nota allí y al revés.
Están separados de `config.json` a propósito: ahí viven las claves de API y
este fichero se reescribe cada vez que se toca un peso.

Este módulo solo lee y escribe; quien lo enseña como menú es `app.py`.
"""
import logging

from puntueitor.core import paths
from puntueitor.core.config import (
    DEFAULT_AVAILABLE_HOURS,
    DEFAULT_MIXED_WEIGHTS,
    DEFAULT_WEIGHTED_WEIGHTS,
    load_scoring,
    save_scoring,
)

logger = logging.getLogger(__name__)

#: Los tres pesos de un formulario "weights", en orden de aparición.
WEIGHT_FIELDS = (
    ("critics", "Críticos"),
    ("users", "Usuarios"),
    ("duration", "Duración"),
)

#: Cuánto puede desviarse la suma de los pesos de 100 y seguir valiendo. El
#: mismo margen que la TUI: son porcentajes escritos a mano y 99.99 no debe
#: dar error.
WEIGHT_SUM_TOLERANCE = 0.1

_DEFAULT_WEIGHTS = {
    "mixed": DEFAULT_MIXED_WEIGHTS,
    "weighted": DEFAULT_WEIGHTED_WEIGHTS,
}


def weights_of(scoring_key: str) -> dict[str, float]:
    """
    Los tres pesos del sistema, EN PORCENTAJE (0-100).

    Por dentro se guardan como fracciones (0.3), pero se enseñan y se
    escriben en porcentaje, igual que en la TUI: es más cómodo escribir "30"
    que "0.3", y así los dos frontales piden lo mismo.
    """
    config = load_scoring()
    return {
        field: getattr(config, f"scoring_{scoring_key}_{field}", 0.0) * 100
        for field, _ in WEIGHT_FIELDS
    }


def weights_sum(values: dict[str, float]) -> float:
    return sum(values.values())


def weights_are_valid(values: dict[str, float]) -> bool:
    return abs(weights_sum(values) - 100.0) <= WEIGHT_SUM_TOLERANCE


def save_weights(scoring_key: str, values: dict[str, float]) -> bool:
    """
    Guarda los pesos si suman 100. Devuelve si se ha guardado.

    Se valida aquí y no al escribir cada valor porque durante la edición es
    normal pasar por estados que no suman 100 (bajas uno para subir otro);
    exigirlo en cada tecla haría imposible repartirlos.
    """
    if not weights_are_valid(values):
        return False

    config = load_scoring()
    for field, _ in WEIGHT_FIELDS:
        setattr(config, f"scoring_{scoring_key}_{field}", values[field] / 100.0)
    save_scoring(config)
    logger.info(f"gui3d: pesos de {scoring_key} guardados: {values}")
    return True


def default_weights(scoring_key: str) -> dict[str, float]:
    defaults = _DEFAULT_WEIGHTS.get(scoring_key, DEFAULT_MIXED_WEIGHTS)
    return {field: defaults[field] * 100 for field, _ in WEIGHT_FIELDS}


def available_hours() -> float:
    return load_scoring().scoring_available_hours or DEFAULT_AVAILABLE_HOURS


def save_available_hours(hours: float) -> None:
    config = load_scoring()
    config.scoring_available_hours = hours
    save_scoring(config)
    logger.info(f"gui3d: horas disponibles guardadas: {hours}")


def preferred_genres() -> set[str]:
    return set(load_scoring().scoring_preferred_genres or [])


def save_preferred_genres(genres) -> None:
    config = load_scoring()
    config.scoring_preferred_genres = sorted(genres)
    save_scoring(config)
    logger.info(f"gui3d: géneros preferidos guardados: {len(genres)}")


def all_genres() -> list[str]:
    """
    Todos los géneros que hay en la caché de IGDB, para poder marcarlos.

    Import local: `IGDBCacher` abre la base de datos al construirse y esto
    solo hace falta si se entra a configurar Genre Match.
    """
    from puntueitor.core.cachers.igdb_cacher import IGDBCacher

    try:
        return list(IGDBCacher(paths.main_db()).get_all_genres())
    except Exception as error:  # pragma: no cover - depende de la caché
        logger.warning(f"gui3d: no se pudieron leer los géneros: {error}")
        return []
