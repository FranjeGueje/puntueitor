# 📦 Puntueitor – Módulos reales para Biblioteca, Filtros y Scoring

Este documento baja el diseño acordado a **módulos Python concretos**, alineados con la arquitectura actual de Puntueitor.

---

## 📁 Estructura propuesta

```
puntueitor/
├─ models/
│  ├─ game.py
│  ├─ library.py
│  └─ selection_context.py
│
├─ filters/
│  ├─ base.py
│  ├─ name.py
│  ├─ genre.py
│  ├─ duration.py
│  └─ score.py
│
├─ scoring/
│  ├─ base.py
│  └─ weighted_score.py
│
├─ selector/
│  └─ score_selector.py
```

---

## 🎮 models/game.py

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Game:
    id: str
    title: str
    genres: list[str]

    duration_hours: float | None = None
    user_score: float | None = None      # 0–100
    critic_score: float | None = None    # 0–100
```

---

## 📚 models/library.py

```python
from __future__ import annotations
from collections.abc import Sequence
from typing import Iterable

from puntueitor.models.game import Game
from puntueitor.filters.base import GameFilter


class GameLibrary:
    def __init__(self, games: Sequence[Game]):
        self._games = list(games)

    @property
    def games(self) -> Sequence[Game]:
        return tuple(self._games)

    def filter(self, *filters: GameFilter) -> GameLibrary:
        games: Iterable[Game] = self._games
        for f in filters:
            games = f.apply(games)
        return GameLibrary(list(games))
```

---

## 🎛 models/selection_context.py

```python
from dataclasses import dataclass


@dataclass(slots=True)
class SelectionContext:
    weight_user_score: float = 0.4
    weight_critic_score: float = 0.4
    weight_duration: float = 0.2

    max_duration: float = 50.0
    missing_data_penalty: float = 0.3
```

---

## 🔍 filters/base.py

```python
from collections.abc import Iterable
from typing import Protocol

from puntueitor.models.game import Game


class GameFilter(Protocol):
    def apply(self, games: Iterable[Game]) -> Iterable[Game]: ...
```

---

## 🔍 filters/name.py

```python
from collections.abc import Iterable

from puntueitor.models.game import Game


class NameFilter:
    def __init__(self, query: str):
        self.query = query.lower().strip()

    def apply(self, games: Iterable[Game]) -> Iterable[Game]:
        return (
            g for g in games
            if self.query in g.title.lower()
        )
```

---

## 🔍 filters/genre.py

```python
from collections.abc import Iterable

from puntueitor.models.game import Game


class GenreFilter:
    def __init__(self, genres: set[str]):
        self.genres = {g.lower() for g in genres}

    def apply(self, games: Iterable[Game]) -> Iterable[Game]:
        return (
            g for g in games
            if self.genres.intersection({x.lower() for x in g.genres})
        )
```

---

## 🔍 filters/duration.py

```python
from collections.abc import Iterable

from puntueitor.models.game import Game


class DurationFilter:
    def __init__(self, max_hours: float):
        self.max_hours = max_hours

    def apply(self, games: Iterable[Game]) -> Iterable[Game]:
        return (
            g for g in games
            if g.duration_hours is not None and g.duration_hours <= self.max_hours
        )
```

---

## ⭐ scoring/base.py

```python
from typing import Protocol

from puntueitor.models.game import Game
from puntueitor.models.selection_context import SelectionContext


class ScoreStrategy(Protocol):
    def score(self, game: Game, ctx: SelectionContext) -> float: ...
```

---

## ⭐ scoring/weighted_score.py

```python
from puntueitor.models.game import Game
from puntueitor.models.selection_context import SelectionContext
from puntueitor.scoring.base import ScoreStrategy


def normalize(value: float, min_: float, max_: float) -> float:
    if max_ <= min_:
        return 0.0
    return max(0.0, min(1.0, (value - min_) / (max_ - min_)))


class WeightedScoreStrategy(ScoreStrategy):
    def score(self, game: Game, ctx: SelectionContext) -> float:
        score = 0.0
        weight_sum = 0.0

        if game.user_score is not None:
            score += ctx.weight_user_score * normalize(game.user_score, 0, 100)
            weight_sum += ctx.weight_user_score
        else:
            score -= ctx.missing_data_penalty

        if game.critic_score is not None:
            score += ctx.weight_critic_score * normalize(game.critic_score, 0, 100)
            weight_sum += ctx.weight_critic_score
        else:
            score -= ctx.missing_data_penalty

        if game.duration_hours is not None:
            duration_score = 1 - normalize(game.duration_hours, 0, ctx.max_duration)
            score += ctx.weight_duration * duration_score
            weight_sum += ctx.weight_duration
        else:
            score -= ctx.missing_data_penalty

        return score / weight_sum if weight_sum > 0 else 0.0
```

---

## 🧠 selector/score_selector.py

```python
from collections.abc import Sequence

from puntueitor.models.game import Game
from puntueitor.models.selection_context import SelectionContext
from puntueitor.scoring.base import ScoreStrategy
from puntueitor.selector.base_selector import BaseGameSelector


class ScoreBasedSelector(BaseGameSelector):
    def __init__(self, strategy: ScoreStrategy):
        self.strategy = strategy

    def select(self, games: Sequence[Game], ctx: SelectionContext) -> Sequence[Game]:
        return sorted(
            games,
            key=lambda g: self.strategy.score(g, ctx),
            reverse=True
        )
```

---

## ✅ Resultado

Con estos módulos ya puedes:

```python
library = GameLibrary(games)

filtered = library.filter(
    NameFilter("hollow"),
    GenreFilter({"metroidvania"}),
    DurationFilter(25),
)

selector = ScoreBasedSelector(WeightedScoreStrategy())

ordered = selector.select(filtered.games, SelectionContext())
```

➡️ Arquitectura limpia, extensible y totalmente alineada con Puntueitor.

---

# 🧩 Enrichers – GameEnricher y HLTB

Este módulo define cómo **fuentes no canónicas** enriquecen un `Game` ya existente, sin crear identidad ni acoplar el dominio a APIs externas.

---

## 🎯 Principios

* Un `GameEnricher` **nunca crea** un `Game`
* **Nunca falla**: si no hay datos, devuelve el juego original
* Añade **atributos atómicos**, no submodelos
* Es reemplazable y componible

---

## 📁 Estructura

```
puntueitor/
├─ enrichers/
│  ├─ base.py
│  └─ hltb.py
│
├─ raw/
│  └─ howlongtobeat/
│     └─ hltb_entry.py
```

---

## 🔌 enrichers/base.py

```python
from typing import Protocol

from puntueitor.models.game import Game


class GameEnricher(Protocol):
    def enrich(self, game: Game) -> Game:
        """
        Enriches a Game with additional data.
        Must never raise and must never create a new identity.
        """
        ...
```

---

## 📦 raw/howlongtobeat/hltb_entry.py

```python
from dataclasses import dataclass


@dataclass(slots=True)
class HLTBEntry:
    hltb_id: int
    name: str
    main_story: float | None
    completionist: float | None
    similarity: float  # 0–1
```

---

## ⏱ enrichers/hltb.py

```python
from dataclasses import replace

from puntueitor.enrichers.base import GameEnricher
from puntueitor.models.game import Game
from puntueitor.raw.howlongtobeat.hltb_entry import HLTBEntry


class HLTBClient:
    """
    Thin wrapper over howlongtobeat API / library.
    Returns raw HLTBEntry objects.
    """

    def search(self, title: str) -> HLTBEntry | None:
        raise NotImplementedError


class HLTBEnricher(GameEnricher):
    def __init__(self, client: HLTBClient, min_similarity: float = 0.7):
        self.client = client
        self.min_similarity = min_similarity

    def enrich(self, game: Game) -> Game:
        try:
            entry = self.client.search(game.title)
        except Exception:
            return game

        if not entry:
            return game

        if entry.similarity < self.min_similarity:
            return game

        if entry.main_story is None:
            return game

        return replace(game, duration_hours=entry.main_story)
```

---

## 🔗 Composición de enrichers

```python
class EnricherPipeline:
    def __init__(self, *enrichers: GameEnricher):
        self.enrichers = enrichers

    def enrich(self, game: Game) -> Game:
        for enricher in self.enrichers:
            game = enricher.enrich(game)
        return game
```

---

## ✅ Uso real

```python
pipeline = EnricherPipeline(
    HLTBEnricher(hltb_client),
)

game = pipeline.enrich(game)
```

---

## 🧠 Resultado arquitectónico

* `Game` sigue siendo limpio
* HLTB es intercambiable
* Puedes añadir:

  * Steam playtime enricher
  * ManualDurationEnricher
  * MetacriticEnricher

Sin tocar el dominio.
































🔹 Resumen arquitectónico y flujo de tu proyecto

1️⃣ Fuentes externas (Input)
APIs externas
├─ Steam → steampy
├─ Epic → epicpy
├─ GOG → gogpy
├─ HLTB → hltbpy

* Cada API devuelve datos crudos (raw)
* Sin lógica de dominio, solo “fetch + parse”


2️⃣ Resolución de identidad (Resolver)
raw data
   ↓
resolvers/
├─ steam_resolver.SteamIGDBResolver
├─ epic_resolver.EpicIGDBResolver
├─ gog_resolver.GogIGDBResolver
└─ hltb_resolver.HLTBIGDBResolver

* Convierte raw → lista de candidatos Game
* Se comunica con IGDB (fuente canónica) si es necesario
* Devuelve siempre list[Game] (posiblemente vacía)

Contrato clave:
resolve(context: SelectionContext, candidates: Sequence[Game]) -> Game | None


3️⃣ Contexto de selección
puntueitor/domain/context.py
└─ SelectionContext

* Representa los datos necesarios para decidir el mejor Game
* Obligatorios: source, title
* Opcionales: release_year, steam_appid, epic_slug, gog_id, etc.
* Permite que el selector tenga información relevante para scoring / heurísticas


4️⃣ Selección del mejor candidato (Selector)
puntueitor/domain/selector.py
├─ BaseGameSelector (abstracto)
└─ SimpleSelector (implementación inicial)

* Recibe: SelectionContext + list[Game]
* Devuelve: Game | None
* Separación de responsabilidades:
    * Resolver → busca candidatos
    * Selector → decide cuál es el “mejor”

Futuro:
* ScoreSelector → scoring más avanzado
* DebugSelector → logs / validación
* Extensible a nuevas heurísticas


5️⃣ Modelo de dominio (Domain)
puntueitor/domain/models.py
└─ Game, HLTBGame, GameCollection

* Representa estado limpio y consistente de un juego
* Mapper: convierte datos crudos de IGDB → Game

puntueitor/domain/mappers.py
└─ map_igdb_to_game(raw) → Game


6️⃣ Enriquecimiento (Enrichers)
puntueitor/enrichers/hltb.py
└─ HLTBIGDBEnricher

* Añade metadatos extra a un Game existente
* Ej: duración HLTB, críticas, reviews
* No decide identidad, solo enriquece


7️⃣ Pipelines (orquestación)
puntueitor/pipelines/
├─ add_igdb_results.py
├─ enrich_with_hltb.py
└─ ...otros futuros pipelines

* Orquesta resolvers + selector + enrichers
* Flujo típico:
raw_data
   ↓ resolve()  → [Game, Game, ...]
   ↓ select(context) → Game
   ↓ enrichers → Game (enriquecido)
   ↓ collection.add(game)

Pipelines son funciones puras de orquestación, sin lógica de negocio propia


8️⃣ Flujo completo (resumido en mapa visual)
┌───────────────┐
│ APIs externas │
│ Steam/Epic/...│
└───────┬───────┘
        │ raw data
        ▼
┌───────────────┐
│   Resolver    │
│ Steam/Epic/...│
└───────┬───────┘
        │ candidates [Game, Game, ...]
        ▼
┌───────────────┐
│   Selector    │
│ (contextual)  │
└───────┬───────┘
        │ Game
        ▼
┌───────────────┐
│  Enrichers    │
│  HLTB, etc.   │
└───────┬───────┘
        │ Game enriquecido
        ▼
┌───────────────┐
│  Collection   │
│ GameCollection│
└───────────────┘

┌────────────────────────────────────────────────────┐
│ -> IGDB funciona como fuente canónica interna      │
│ -> Todo pasa por modelo limpio (Game)              │
│ -> Selector y enrichers no hacen I/O → dominio puro│
│ -> Pipelines solo orquestan                        │
└────────────────────────────────────────────────────┘


9️⃣ Nombres clave y módulos
Concepto	        Módulo/fichero	            Rol
─────────────────────────────────────────────────────────────────────────
Resolver	        resolvers/steam.py, etc.	Raw → candidatos Game
Contexto	        domain/context.py	        Info necesaria para seleccionar
Selector	        domain/selector.py	        Elegir mejor Game
Modelo	            domain/models.py	        Estado limpio Game/HLTBGame
Mapper	            domain/mappers.py	        Transformar raw IGDB → Game
Enricher	        enrichers/hltb.py	        Añadir metadatos extra
Pipeline	        pipelines/*.py	            Orquestar todo



🔹 Observaciones finales
* La arquitectura no cambia, solo mejoras de flujo:
    * Ahora el selector usa contexto
    * Resolver → candidates
    * Selector → decisión
    * Enrichers → metadatos
    * Pipelines → orquestación
* Todo está tipado y limpio
* Fácil de testear: puedes mockear resolvers y selector por separado
