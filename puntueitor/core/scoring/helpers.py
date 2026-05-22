def score_or_steam(value: float | None, steam_value: float | None) -> float:
    if value and value > 0:
        return value / 100.0
    if steam_value and steam_value > 0:
        return steam_value / 100.0
    return 0.0
