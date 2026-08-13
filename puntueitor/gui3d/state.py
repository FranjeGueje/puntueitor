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

from puntueitor.core import paths
from puntueitor.core.config import write_json_atomic
from puntueitor.gui3d.filters import Filters

logger = logging.getLogger(__name__)

_FILTERS_KEY = "filters"


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
