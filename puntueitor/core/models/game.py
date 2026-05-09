from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path

from .util import normalize_title


class Stores(StrEnum):
    STEAM = "steam"
    EPIC = "epic"
    GOG = "gog"


StoreMap = dict[Stores, str]


@dataclass(slots=True)
class Game:
    # 🔑 Identidad canónica
    igdb_id: int

    # 🧠 Identidad humana
    title: str
    title_normalized: str = field(init=False)

    # 📚 Dominio
    genres: tuple[str, ...] = field(default_factory=tuple)
    storyline: str | None = None
    release_date: date | None = None
    cover_url: str | None = None

    # 📊 Métricas atómicas
    critic_score: float | None = None    # 0–100
    user_score: float | None = None      # 0–100
    duration_hours: float | None = None  # enriquecido (HLTB u otro)

    # 🔗 Metadatos externos
    stores: StoreMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title_normalized = normalize_title(self.title)

    # ──────────────────────────────
    # 🔢 Derivados (NO persistidos)
    # ──────────────────────────────

    # ──────────────────────────────
    # 🏬 Stores
    # ──────────────────────────────

    def set_store(self, store: Stores, store_id: str) -> None:
        if not store_id:
            raise ValueError("Store id cannot be empty")
        self.stores[store] = store_id

    # ──────────────────────────────
    # 💾 Serialización
    # ──────────────────────────────

    def to_dict(self) -> dict:
        return {
            "igdb_id": self.igdb_id,
            "title": self.title,
            "genres": self.genres,
            "storyline": self.storyline,
            "release_date": self.release_date.isoformat() if self.release_date else None,
            "cover_url": self.cover_url,
            "critic_score": self.critic_score,
            "user_score": self.user_score,
            "duration_hours": self.duration_hours,
            "stores": {k.value: v for k, v in self.stores.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> Game:
        stores: StoreMap = {}
        for k, v in data.get("stores", {}).items():
            try:
                stores[Stores(k)] = v
            except ValueError:
                pass

        release_date = (
            date.fromisoformat(data["release_date"])
            if data.get("release_date")
            else None
        )

        return cls(
            igdb_id=data["igdb_id"],
            title=data["title"],
            genres=tuple(data.get("genres", [])),
            storyline=data.get("storyline"),
            release_date=release_date,
            cover_url=data.get("cover_url"),
            critic_score=data.get("critic_score"),
            user_score=data.get("user_score"),
            duration_hours=data.get("duration_hours"),
            stores=stores,
        )

    def to_disk(self, path: str | Path) -> None:
        path = Path(path)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def from_disk(cls, path: str | Path) -> Game:
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Invalid Game file")
        return cls.from_dict(data)
