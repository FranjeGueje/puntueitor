from puntueitor.core.models.util import is_missing


def score_or_steam(value: float | None, steam_value: float | None) -> float:
    """
    Normaliza una puntuación 0–100 a 0.0–1.0, recurriendo a la de Steam
    cuando la de IGDB no está disponible.
    """
    if not is_missing(value):
        return value / 100.0
    if not is_missing(steam_value):
        return steam_value / 100.0
    return 0.0
