import re
from difflib import SequenceMatcher

# Compilados a nivel de módulo: normalize_title se llama una vez por cada Game
# construido, así que recompilar aquí dentro dominaba el coste de la carga.
_BRACKET_PATTERNS = (
    re.compile(r'\(.*?\)'),
    re.compile(r'\[.*?\]'),
    re.compile(r'[:\-–]'),
)

# El orden importa: 'deluxe edition' debe intentarse antes que 'edition'.
_EDITION_WORDS = re.compile(
    r'\b(?:remastered|definitive|goty|complete|deluxe edition|edition'
    r'|enhanced|collection|bundle|pack)\b'
)

_WHITESPACE = re.compile(r'\s+')


def normalize_title(title: str) -> str:
    title = title.lower()

    for pattern in _BRACKET_PATTERNS:
        title = pattern.sub(' ', title)

    title = _EDITION_WORDS.sub(' ', title)

    return _WHITESPACE.sub(' ', title).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def is_missing(value: float | None) -> bool:
    """
    Convención única del proyecto para puntuaciones ausentes.

    Las fuentes externas (IGDB, Steam) devuelven 0 tanto para "sin datos" como
    para "puntuación cero", y en la práctica una valoración real de 0 sobre 100
    no existe. Cualquier valor no positivo cuenta como ausencia, para que
    scoring, sorting y filtros compartan criterio.

    Ojo: `duration_hours` NO usa esto — ahí `None` es el único valor de
    ausencia y 0.0 sería una duración legítima.
    """
    return value is None or value <= 0.0
