from dataclasses import dataclass

@dataclass(frozen=True)
class ScoringContext:
    available_hours: float | None = None
    preferred_genres: set[str] | None = None
    disliked_genres: set[str] | None = None
    title_query: str | None = None
