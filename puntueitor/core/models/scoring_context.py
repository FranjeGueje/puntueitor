from dataclasses import dataclass

@dataclass(frozen=True)
class ScoringContext:
    available_hours: float | None = None
    preferred_genres: set[str] | None = None
    disliked_genres: set[str] | None = None
    title_query: str | None = None

    # Configuración de scoring
    duration_scale: float = 80.0
    neutral_duration_score: float = 0.5
    ideal_duration: float = 15.0
    max_duration: float = 60.0
