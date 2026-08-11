# Arquitectura y Guía de Diseño de Puntueitor 🏗️

> [!NOTE]
> Este documento representa la **fusión corregida, unificada y actualizada** de los antiguos archivos de fase temprana `arquitectura.md` y `LEEME.txt`. Se han enmendado todas las discrepancias y desviaciones respecto al código fuente de producción actual de **Puntueitor** (construido sobre Python 3.14 con arquitectura limpia y DDD).

---

## 🗺️ Estructura Real de Módulos (Core)

En la fase inicial de diseño se plantearon paquetes planos directos (`puntueitor/models/`, `puntueitor/filters/`, etc.). En el sistema en producción, todo el núcleo de lógica de negocio y dominio se encuentra agrupado bajo el módulo encapsulado `core/`, garantizando una separación limpia de la interfaz de usuario (`gui/`):

```text
puntueitor/
├── core/
│   ├── cachers/       # Cachés locales (SQLite) de IGDB, tiendas, estado de librería y HLTB
│   │                  # Todos sobre BaseCacher: conexión por hilo, esquema y errores
│   ├── config.py      # Gestor singleton ConfigManager para ~/.config/puntueitor/config.json
│   ├── enrichers/     # Complemento de metadatos no canónicos (HLTBEnricher)
│   ├── filters/       # Predicados booleanos puros de juegos (matches)
│   ├── heroics/       # Lector de librerías de Heroic Games Launcher (GOG, Epic, Amazon)
│   ├── igdb/          # Cliente y autenticador de la API IGDB (igdbpy)
│   ├── mappers/       # Conversión stateless de esquemas externos a modelos del dominio
│   ├── models/        # Entidades inmutables y de dominio (Game, Library, Contexts)
│   ├── pipeline/      # Orquestación de carga asíncrona concurrente de datos (hilos)
│   ├── protocols/     # Interfaces y contratos del sistema (PEP 544 Protocols)
│   ├── raw/           # Estructuras de datos puras de llamadas web (HLTBEntry)
│   ├── repository/    # Carga y serialización agregada unificando caché y estado de usuario
│   ├── resolvers/     # Estrategias de correlación por tienda contra IGDB
│   ├── scoring/       # Algoritmos y coeficientes de recomendación multi-criterio
│   ├── selector/      # Criterios de desambiguación de candidatos duplicados
│   ├── services/      # Fachada API para el consumo desde la GUI (LibraryService)
│   └── sorting/       # Estrategias puras de ordenación
├── gui/               # Interfaz gráfica TUI basada en Textual (pantallas y widgets)
└── steampy/           # Submódulo independiente cliente de la API de Steam (rate-limited)
```

---

## 🎮 1. El Modelo del Dominio (`core/models/`)

El modelo propuesto en fases tempranas planteaba un `GameLibrary` mutable con filtros integrados y una entidad `Game` con IDs en formato `str`. En producción, el modelo se ha depurado bajo principios de inmutabilidad y eficiencia de memoria (`slots=True`):

### Títulos, Identidad y Estados (`game.py`)
```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

class Stores(StrEnum):
    STEAM = "steam"
    EPIC = "epic"
    GOG = "gog"
    AMAZON = "amazon"

StoreMap = dict[Stores, str]

@dataclass(slots=True)
class Game:
    igdb_id: int                         # Identidad canónica unificada (IGDB)
    title: str                           # Nombre del juego
    title_normalized: str = field(init=False)

    genres: tuple[str, ...] = field(default_factory=tuple)
    storyline: str | None = None
    release_date: date | None = None
    cover_url: str | None = None

    critic_score: float | None = None    # 0–100 (IGDB Aggregated Rating)
    user_score: float | None = None      # 0–100 (IGDB Rating)
    duration_hours: float | None = None  # Enriquecido desde HLTB u otros cachers
    steam_score: float | None = None     # 0–100 (Enriquecido desde reseñas de Steam)
    steam_review: int | None = None      # 0-9 (Categoría de review en Steam)

    stores: StoreMap = field(default_factory=dict) # Enlaces con IDs en tiendas

    # Estados editables locales del perfil de usuario
    finished: bool = False
    hidden: bool = False
    backlog: bool = False
    favorite: bool = False

    def __post_init__(self) -> None:
        from .util import normalize_title
        self.title_normalized = normalize_title(self.title)

    def set_store(self, store: Stores, store_id: str) -> None:
        if not store_id:
            raise ValueError("Store id cannot be empty")
        self.stores[store] = store_id
```

### Colección de Biblioteca (`library.py`)
En lugar de la clase mutable `GameLibrary` de la fase de diseño inicial, la biblioteca en producción (`Library`) es un contenedor **inmutable** y congelado:
```python
from dataclasses import dataclass
from collections.abc import Iterable, Iterator
from .game import Game

@dataclass(frozen=True)
class Library:
    games: tuple[Game, ...]

    @classmethod
    def from_iterable(cls, games: Iterable[Game]) -> Library:
        return cls(tuple(games))

    def __iter__(self) -> Iterator[Game]:
        return iter(self.games)

    def __len__(self) -> int:
        return len(self.games)

    def contains_igdb_id(self, igdb_id: int) -> bool:
        return any(g.igdb_id == igdb_id for g in self.games)
```

---

## 🔌 2. Contratos y Abstracciones (`core/protocols/`)

En el diseño temprano, los filtros utilizaban una interfaz pesada basada en lotes (`apply(self, games: Iterable[Game]) -> Iterable[Game]`). En producción, se ha simplificado a predicados unitarios (`matches`) siguiendo el patrón **Filter**, lo que permite combinar filtros con operadores lógicos AND / OR sencillos en pipelines:

```python
from typing import Protocol, runtime_checkable
from collections.abc import Sequence
from puntueitor.core.models import Game, ScoringContext, SelectionContext, Library

class GameFilter(Protocol):
    """Predicado puro unitario sobre una entidad Game."""
    def matches(self, game: Game) -> bool: ...

class GameScorer(Protocol):
    """Calcula una valoración numérica flotante para un juego en un contexto."""
    def score(self, game: Game, ctx: ScoringContext) -> float: ...

class GameSelector(Protocol):
    """Resuelve la ambigüedad eligiendo el mejor juego de una lista de candidatos."""
    def select(self, candidates: Sequence[Game], ctx: SelectionContext) -> Game | None: ...

@runtime_checkable
class GameEnricher(Protocol):
    """Complementa un juego existente. No debe fallar ni crear nuevas identidades."""
    def enrich(self, game: Game) -> Game: ...

class GameSorter(Protocol):
    """Ordena una biblioteca de juegos."""
    def sort(self, library: Library) -> Library: ...
```

---

## 🔍 3. Implementaciones de Filtros (`core/filters/`)

Todos los filtros del sistema implementan `GameFilter` a nivel unitario (`matches`):

* **`NameFilter` (`name_filter.py`)**:
  Realiza tres comprobaciones jerárquicas:
  1. ¿El título normalizado de la query está dentro del título normalizado del juego?
  2. ¿El título normalizado está dentro del título original (por si acaso)?
  3. Si falla la subcadena, calcula un ratio tipográfico fuzzy (`core/models/util.py:similarity`) evaluando si supera el umbral configurable (por defecto `0.8`).
* **`DurationFilter` (`duration_filter.py`)**:
  Retorna `True` si la duración estimada del juego es menor o igual al límite. Si el juego carece de duración, se le permite pasar por defecto (`True`).
* **`FinishedFilter` / `FavoriteFilter` / `BacklogFilter` / `HiddenFilter`**:
  Comprueban directamente si el estado booleano de la clase de dominio `Game` coincide con el valor buscado.

---

## ⭐ 4. Motor de Scoring y Selección (`core/scoring/` y `core/selector/`)

### Contextos en Producción
El diseño conceptual inicial integraba la lógica de pesos de puntuación en `SelectionContext`. En producción se han separado dos responsabilidades críticas:
1. **`SelectionContext` (`core/models/selection_context.py`)**: Lleva identificadores informativos de procedencia de red para desambiguar correlaciones (`steam_appid`, `epic_slug`, `gog_id`, `release_year`).
2. **`ScoringContext` (`core/models/scoring_context.py`)**: Lleva los parámetros del algoritmo (horas de juego disponibles del usuario, géneros preferidos, géneros odiados, y umbrales de duración).

### Estrategias de Scoring (`core/scoring/`)
Todas las estrategias heredan del protocolo `GameScorer`:
* **`MixedScore`**: Combina tres variables:
  * Valoración de la crítica (normalizada $0.0 - 1.0$ usando fallback a `steam_score` si no hay IGDB).
  * Valoración de los usuarios (normalizada $0.0 - 1.0$ usando fallback a `steam_score` si no hay IGDB).
  * Duración ponderada mediante un decaimiento exponencial: $e^{-\frac{\text{duración}}{\text{escala}}}$.
* **`WeightedScore`**: Ejecuta una colección configurable de sub-scorers (`CriticScoreScorer`, `UserScoreScorer`, `DurationScoreScorer` todos con soporte para fallback a Steam a través de la función utilitaria `score_or_steam` de `helpers.py`) y multiplica sus retornos por pesos definidos en la configuración de usuario.
* **`AvailableTimeScorer`**: Puntúa de acuerdo a una ventana temporal libre:
  * Si la duración es menor o igual a las horas disponibles, otorga una puntuación excelente priorizando los juegos que saquen mayor partido a la ventana.
  * Si sobrepasa la ventana, aplica penalizaciones lineales proporcionales al exceso.
* **`GenreScorer`**: Suma peso si el juego contiene géneros preferidos por el usuario, y resta drásticamente (`-1.0`) si incluye géneros marcados como intolerables (odiados).

### Selectores y Desambiguación (`core/selector/`)
* **`SteamSelector`**: Resuelve colisiones de múltiples candidatos devueltos por consultas generales de IGDB. Utiliza una fórmula híbrida que combina el score básico del juego con el grado de completitud de su ficha técnica (si dispone de carátula, sinopsis, horas y notas), eligiendo la ficha más rica.
* **`HLTBSelector`**: Heurística para escoger el mejor match devuelto por la API de HowLongToBeat.

---

## 🗄️ 5. Arquitectura de Datos Separada (`core/cachers/` y `core/repository/`)

El diseño inicial de `LEEME.txt` ignoraba las colisiones entre datos globales y locales. En producción, la **Capa de Persistencia** sigue una separación estricta para cumplir con la arquitectura offline-first:

```text
                                  ┌───────────────────────────┐
                                  │   ~/.cache/puntueitor/    │
                                  │       puntueitor.db       │
                                  └─────────────┬─────────────┘
                                                │
                               ┌────────────────┼────────────────┐
                               ▼                ▼                ▼
                        ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
                        │    games    │  │  resolvers  │  │   extras    │
                        │ (Canónicos) │  │(Resolución) │  │   (HLTB)    │
                        └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
                               │                │                │
                               └────────┐       │       ┌────────┘
                                        ▼       ▼       ▼
                                ┌──────────────────────────┐
                                │    LibraryRepository     │ <─── [Hidrata en memoria]
                                └───────────▲──────────────┘
                                            │
                               ┌────────────┴────────────┐
                               │  ~/.config/puntueitor/  │
                               │     library.sqlite      │
                               │ (Estados: terminado...) │
                               └─────────────────────────┘
```

1. **`puntueitor.db`**: SQLite global que centraliza información pesada inmutable.
   * `games` (`IGDBCacher`): Respuestas JSON nativas de IGDB. Incluye soporte para el almacenamiento persistente de `steam_id` mapeado a partir de la API de IGDB.
   * `resolvers` (`ResolversCacher`): Tabla relacional que correlaciona `(store_name, store_game_id)` $\to$ `igdb_id`.
   * `extras` (`ExtrasCacher`): Duraciones estimadas de juego (HLTB) y valoraciones de Steam (`steam_score`, `steam_review`).
   * `desconocidos` (`DesconocidosCacher`): Registro de IDs externos que no existen en IGDB para evitar búsquedas repetitivas de red en el inicio.
2. **`library.sqlite`** (`LibraryCacher`):
   * Guarda únicamente las columnas editables del usuario (`finished`, `hidden`, `backlog`, `favorite`) indexadas por el `igdb_id` canónico.
3. **`LibraryRepository.load()`**:
   * Lee la tabla relacional de resolvers activos.
   * Carga las especificaciones de juego correspondientes desde la caché global de IGDB.
   * Inyecta las duraciones estimadas e información de reseñas de Steam desde la caché de extras.
   * Consulta las banderas de usuario en la base de datos de configuración local.
   * Instancia e hidrata de forma limpia la colección inmutable `Library`.

---

## 🔄 6. Pipelines y Carga Concurrente (`core/pipeline/`)

Las pipelines actúan como casos de uso u orquestadores puros sin estado, encargados de coordinar componentes.

* **`load_library` (`load_steam_library.py`)**:
  Orquesta la carga general de juegos a través de un pool de hilos de ejecución concurrentes (`ThreadPoolExecutor`):
  1. Detecta plataformas activas en la configuración.
  2. Lanza de forma asíncrona la descarga de juegos en propiedad de Steam (mediante `steampy`) y lee las bases de datos de Heroic Games Launcher para Epic, GOG y Amazon.
  3. Ejecuta la resolución de identidades a través de los `Resolvers` e invoca al `Selector` para filtrar candidatos falsos.
  4. Envía de forma paralela peticiones a los enriquecedores activos (como el de HowLongToBeat y el de Steam Reviews **`SteamScoreEnricher`** en background) para actualizar estimaciones y notas de juego, alimentando la interfaz en tiempo real mediante callbacks de progreso y cargando instantáneamente desde el caché local `extras` si los datos ya residen allí.
* **`EnrichmentPipeline`**: Aplica de manera segura una lista de `GameEnricher` secuenciales sobre los elementos de una biblioteca.

---

## 🔌 7. Submódulo de API de Steam (`steampy/`)

Ubicado de forma independiente del núcleo de negocio, actúa como cliente HTTP puro para la plataforma de Valve.
* **Rate Limiting**: Utiliza un búfer temporal (`threading.Lock` y ventanas de tiempo basado en `time.monotonic()`) para evitar sobrepasar los límites de llamadas de la Steam Web API.
* **Caché Relacional**: Almacena las respuestas de la lista de juegos del usuario (`owned_games`) directamente en `cache/{steam_id}.sqlite` para mitigar el consumo de red en arranques consecutivos.

---

## 🚀 Resumen de Diferencias: Diseño Conceptual vs Implementación Real

| Concepto / Componente | Propuesta en Fase Temprana (`arquitectura.md`/`LEEME.txt`) | Implementación de Producción de Alta Cohesión |
| :--- | :--- | :--- |
| **Ubicación del Core** | Módulos planos en la raíz (`puntueitor/models/`, `puntueitor/filters/`) | Encapsulado bajo el módulo coherente `puntueitor/core/` |
| **Entidad `Game`** | Usaba `id: str` e ignoraba los estados mutables de interacción. | Identidad en `igdb_id: int` canónico, con persistencia aislada de estados del usuario. |
| **Clase `Library`** | Llamada `GameLibrary`, con lógica interna de filtrado mutable. | `Library` es una `dataclass` inmutable con `tuple[Game]`. Las operaciones se delegan. |
| **Contrato de Filtros** | Método pesado por lotes `apply(self, games: Iterable[Game])`. | Protocolo unitario `matches(self, game: Game) -> bool` ideal para composición AND/OR. |
| **Contrato de Scoring** | Método `score(self, game, SelectionContext)` | Protocolo puro `score(self, game, ScoringContext)` desacoplado de IDs de selección. |
| **Separación de Datos** | Sin estrategia de persistencia (se mezclaban campos locales y externos). | "Golden Rule": Datos de red en base de datos global; estados de usuario en SQLite local. |
| **Carga de Datos** | Secuencial síncrona en pipelines planos. | Asíncrona con pool de hilos (`ThreadPoolExecutor`) y callbacks dinámicos de progreso. |
