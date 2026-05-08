from dataclasses import dataclass
from enum import Enum


class SourceContext(Enum):
    STEAM = "steam"
    EPIC = "epic"
    GOG = "gog"
    HLTB = "hltb"


@dataclass(frozen=True)
class SelectionContext:
    title: str
    source: SourceContext | None = None
    release_year: int | None = None

    # ids opcionales según fuente
    steam_appid: str | None = None
    epic_slug: str | None = None
    gog_id: str | None = None