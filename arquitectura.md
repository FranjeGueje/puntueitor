# Arquitectura de Puntueitor 🏗️

Puntueitor unifica bibliotecas de varias tiendas (Steam, GOG, Epic, Amazon),
las identifica contra IGDB, las enriquece con duraciones de HowLongToBeat y
puntuaciones de Steam, y calcula recomendaciones con criterios combinables.

Este documento explica **por qué** el sistema está montado así. Lo que se
puede deducir leyendo el código —qué módulos hay, qué campos tiene cada
clase, qué hace cada función— no está aquí a propósito: esa clase de
documentación se desincroniza a la primera y entonces miente, que es peor
que no existir. Para el "qué", el código; aquí el "por qué".

> Este fichero sustituye a `DOC.md` y a la versión anterior de
> `arquitectura.md`, que eran el mismo documento escrito dos veces y ya
> habían derivado: entre los dos documentaban un módulo `core/index/`, una
> clase `LibraryIndex` y un patrón `CompositeGameScorer` que no existen, un
> campo `steam_score` que en realidad son tres (`steamdb_score`,
> `review_pos`, `review_neg`), una tabla `desconocidos` que se llama
> `unknown_games`, y rutas de datos que cambiaron.

---

## 🏆 La Regla de Oro

Es la invariante central del sistema y de la que dependen el repositorio, la
carga y los dos frontends:

**La tabla `resolvers` es la única fuente de verdad de qué juegos están en
la biblioteca.**

La tabla `games` NO lo es, aunque lo parezca. `games` es la caché global de
*toda* consulta hecha a IGDB, e incluye candidatos de búsqueda descartados
al resolver otros títulos: buscar por título devuelve varios resultados, se
cachean todos y solo se elige uno. Recorrer `games` directamente cuela esos
huérfanos —juegos con carátula pero sin ninguna tienda, que nunca estuvieron
en la biblioteca. Es un error que ya se ha cometido dos veces; la segunda,
en el frontend 3D.

Quien quiera leer la biblioteca debe usar `LibraryRepository.load()`, que
además es el único sitio donde se une todo: resolvers + fichas de IGDB +
extras + estados del usuario.

---

## 🗄️ Separación de datos

Tres clases de datos con dueños y ciclos de vida distintos, deliberadamente
en ficheros separados:

| Dato | Dónde | Se puede regenerar |
|---|---|---|
| Fichas de IGDB (`games`) | `puntueitor.db` | Sí, volviendo a consultar |
| Correlaciones (`resolvers`), extras HLTB/Steam, `unknown_games` | `puntueitor.db` | Sí, pero a base de miles de llamadas |
| Marcas del usuario (`user_games`) | `library.sqlite` | **No** |

Las marcas del usuario (terminado, oculto, pendiente, favorito) viven en su
propio fichero y no mezcladas con la caché de red, precisamente para que
borrar lo segundo no se lleve nunca lo primero por delante.

Las dos bases están en `~/.local/share/puntueitor/`, no en `~/.cache`. El
reparto completo de directorios, y el porqué, está en `core/paths.py`.

Todos los cachers heredan de `BaseCacher`, que aporta conexión por hilo
(SQLite en modo WAL, para que los enrichers puedan escribir desde el pool
mientras la interfaz lee), esquema declarado una sola vez y degradación
controlada: un fallo puntual se registra y sigue, solo un fallo de
inicialización marca el cacher como no disponible.

---

## 🔄 Flujo de carga

```mermaid
graph TD
    A[Tiendas<br>Steam API · Heroic: GOG, Epic, Amazon] --> B[Resolvers<br>identidad externa → IGDB]
    B --> C[IGDB Service<br>consulta + caché]
    C --> D[Mappers<br>JSON de IGDB → modelo de dominio]
    D --> E[Selector<br>desambigua candidatos]
    E --> F[Enrichers<br>HLTB · Steam reviews]
    F --> G[Cachers + LibraryRepository]
    G --> H[LibraryService]
    H --> I[gui/ TUI · gui3d/ carrusel 3D]
```

`load_steam_library.py` orquesta todo eso sobre un `ThreadPoolExecutor`, con
callbacks de progreso para que la interfaz vaya mostrando resultados en vez
de esperar al final. Con bibliotecas de más de mil juegos la diferencia no
es cosmética.

---

## 🎯 Decisiones de diseño

Estas son las que no se deducen del código, y las que conviene entender
antes de tocar nada.

**`igdb_id: int` como identidad canónica.** Cada tienda tiene su propio
identificador y ninguno sirve fuera de ella. IGDB actúa de eje: todo lo
demás cuelga de ahí, incluidas las marcas del usuario, que así sobreviven a
que un juego cambie de tienda o se compre dos veces.

**`Library` inmutable.** Es una `dataclass` congelada sobre una tupla, sin
lógica de filtrado dentro. Filtrar, ordenar y puntuar son operaciones que
devuelven cosas nuevas, no que mutan la colección. Evita toda una familia de
errores en la que la interfaz y el core dejan de ver lo mismo.

**Los filtros son predicados unitarios (`matches(game) -> bool`), no
operaciones por lotes.** Con un predicado se pueden combinar filtros con AND
y OR trivialmente; con una interfaz `apply(games) -> games` cada composición
hay que escribirla a mano.

**`ScoringContext` y `SelectionContext` están separados** aunque al
principio fueran uno. Llevan cosas distintas y se usan en momentos
distintos: el de selección lleva identificadores de procedencia para
desambiguar (`steam_appid`, `gog_id`, slug, año); el de scoring lleva
preferencias del usuario (horas disponibles, géneros preferidos y odiados).
Juntarlos obligaba a construir un objeto enorme y medio vacío en ambos
casos.

**Los mappers son barrera anticorrupción.** `IGMapperGame` es el único sitio
que sabe cómo es el JSON de IGDB. Si IGDB cambia una clave, se arregla ahí y
el resto del core ni se entera.

**`steampy/` está fuera del core** y es un cliente HTTP puro, con rate
limiting propio (ventana temporal + `threading.Lock`) para no quemar la
clave de API del usuario.

---

## 🔍 Resolvers: una estrategia por tienda

Esta parte sí merece explicación, porque cada tienda obliga a un truco
distinto y no es evidente por qué:

| Tienda | Estrategia | Por qué |
|---|---|---|
| **Steam** | `external_game_source = 1` + appid | IGDB indexa los appid de Steam directamente |
| **GOG** | `external_game_source = 5` + id de Heroic | Igual que Steam, con su propia fuente |
| **Epic** | Extrae el *slug* de la URL y busca por él | Epic no tiene correlación de id estable en IGDB |
| **Amazon** | Búsqueda por título + compara fecha de lanzamiento | No hay id ni slug; la fecha es lo que separa secuelas y remakes del original |

Todos caen a búsqueda por título normalizado si su vía principal falla, y de
ahí pasan al `Selector`, que elige entre candidatos combinando la nota del
juego con lo completa que esté su ficha (carátula, sinopsis, duración,
notas). Lo que no se resuelve va a `unknown_games` para no repetir la
búsqueda en cada arranque.

---

## 💎 Patrones

- **Strategy** — scorers, filtros y sorters detrás de `Protocol`s (PEP 544).
  La interfaz cambia de fórmula en caliente sin tocar el motor.
- **Facade** — `LibraryService` es el único punto de contacto para los
  frontends. Ni la TUI ni `gui3d/` conocen cachers ni pipelines.
- **Repository** — `LibraryRepository` esconde que la biblioteca sale de
  cuatro tablas en dos ficheros.
- **Anticorruption layer** — los mappers, arriba.

---

## 🚀 Cómo extender

### Añadir una tienda
1. Amplía el enum `Stores` en `core/models/game.py`.
2. Crea un resolver que herede de `BaseResolver` en `core/resolvers/`, con
   `resolve(raw, refresh) -> Sequence[Game]`. Mira primero si IGDB indexa
   esa tienda en `external_games`; si no, tocará slug o título + fecha.
3. Engánchalo en `core/pipeline/load_steam_library.py`.

### Añadir una fórmula de puntuación
1. Implementa `GameScorer` en `core/scoring/atomic/` (o en `core/scoring/`
   si compone otras).
2. `score(game, ctx) -> float`, normalizado.
3. Regístrala en `_get_scorer` de `core/services/library_service.py`.

### Añadir un enriquecedor
1. Implementa `GameEnricher` en `core/enrichers/`.
2. `enrich(game) -> Game`, apoyándote en `dataclasses.replace`.
3. Añádelo a la lista de enrichers de `load_steam_library.py`.
4. Si guarda datos nuevos, van a la tabla `extras`, no a `games`: `games`
   es caché de IGDB y se puede borrar entera.

---

## 📎 Documentos relacionados

- `README.md` — instalación, configuración y uso.
- `AGENTS.md` — notas de trabajo: trampas concretas encontradas, cómo se
  midieron y por qué ciertas constantes valen lo que valen. Es donde va lo
  que costó horas averiguar y no se puede reconstruir leyendo el código.
- `CHANGELOG.md` — historial de versiones.
