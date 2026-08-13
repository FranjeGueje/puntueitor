"""
Estado de gui3d que sobrevive entre sesiones (`gui3d.json`, ver
`core.paths.gui3d_state_file`).

Aparte de `filters.py` a propósito: allí vive el MODELO de los filtros (qué
significa cada campo, cómo se aplican), aquí solo la lectura/escritura a
disco. Ese reparto es el mismo que ya usa `scoring_config.py` frente a
`core/config.py`.

Se guarda bajo una clave por "cosa a recordar" dentro de un único dict de
nivel superior (hoy solo `"filters"`), no el contenido directamente, para
poder añadir otras cosas más adelante (qué puntuación enseñar en la
pegatina de la caja, por ejemplo) sin tener que migrar nada. `save_filters`
relee el fichero antes de escribir y solo toca su propia clave, así que una
clave futura que ya exista no se pierde por guardar los filtros — mismo
criterio que `ConfigManager.save()` en `core/config.py`.
"""
import dataclasses
import json
import logging
from dataclasses import dataclass

from puntueitor.core import paths
from puntueitor.core.config import write_json_atomic
from puntueitor.gui3d.filters import Filters

logger = logging.getLogger(__name__)

_FILTERS_KEY = "filters"
_PREFERENCES_KEY = "preferences"

#: Qué nota se pinta dentro de la estrella de cada caja, y el orden en que
#: rota al pulsar izquierda/derecha en el menú GUI3D. Cada valor es la mitad
#: de un nombre de campo de `Game`: "user" -> `user_score` (ver
#: `case_labels.score_field`).
SCORE_SOURCES = ("steamdb", "user", "critic")

DEFAULT_SCORE_SOURCE = SCORE_SOURCES[0]


@dataclass
class Preferences:
    """Ajustes del frontend 3D que sobreviven entre sesiones."""

    #: Cuál de las tres notas se enseña en la pegatina de la caja.
    score_source: str = DEFAULT_SCORE_SOURCE

    #: Si los filtros del carrusel se recuperan al arrancar. En False no se
    #: BORRA lo guardado, solo se deja de leer y de escribir: volver a
    #: activarlo recupera los filtros de la última vez.
    save_filters: bool = True


def _read() -> dict:
    path = paths.gui3d_state_file()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as error:
        logger.warning(f"gui3d: no se pudo leer {path}: {error}")
        return {}


def load_filters() -> Filters:
    """
    Los filtros guardados, o los de siempre (todo sin filtrar) si no hay
    nada guardado o el fichero no se entiende.

    Se queda solo con los nombres de campo que `Filters` reconoce HOY, igual
    que `Config`/`ScoringConfig` en `core/config.py`: así un `gui3d.json` de
    una versión anterior o posterior (con un campo de menos o de más) no
    rompe el arranque, simplemente ignora lo que no encaja.
    """
    data = _read().get(_FILTERS_KEY)
    if not isinstance(data, dict):
        return Filters()
    names = {f.name for f in dataclasses.fields(Filters)}
    return Filters(**{k: v for k, v in data.items() if k in names})


def save_filters(filters: Filters) -> None:
    state = _read()
    state[_FILTERS_KEY] = dataclasses.asdict(filters)
    write_json_atomic(paths.gui3d_state_file(), state)


def load_preferences() -> Preferences:
    """
    Los ajustes guardados, o los de siempre si no hay nada o no se entiende.

    `score_source` se valida contra `SCORE_SOURCES` en vez de aceptarse tal
    cual: este fichero se puede editar a mano, y un valor inventado dejaría
    la aplicación buscando un campo que no existe en `Game` cada vez que
    pinta una caja.
    """
    data = _read().get(_PREFERENCES_KEY)
    if not isinstance(data, dict):
        return Preferences()

    names = {f.name for f in dataclasses.fields(Preferences)}
    prefs = Preferences(**{k: v for k, v in data.items() if k in names})

    if prefs.score_source not in SCORE_SOURCES:
        logger.warning(
            f"gui3d: puntuación desconocida {prefs.score_source!r}; "
            f"se usa {DEFAULT_SCORE_SOURCE!r}"
        )
        prefs.score_source = DEFAULT_SCORE_SOURCE

    return prefs


def save_preferences(prefs: Preferences) -> None:
    state = _read()
    state[_PREFERENCES_KEY] = dataclasses.asdict(prefs)
    write_json_atomic(paths.gui3d_state_file(), state)
