from dataclasses import dataclass

@dataclass(slots=True)
class HLTBEntry:
    hltb_id: int
    name: str
    main_story: float | None
    main_extra: float | None
    completionist: float | None
    similarity: float # 0–1
    url: str | None