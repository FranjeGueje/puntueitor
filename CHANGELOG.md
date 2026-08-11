# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

## [1.1.0] - 2026-08-11

### Corregido

- **Regresión crítica del centinela de duración HLTB**: `HLTBEnricher` ya no
  escribe `duration_hours = 0` cuando no encuentra un juego en HowLongToBeat.
  Ese `0` se interpretaba como una duración real de cero horas y hacía que
  los juegos sin duración conocida puntuasen al máximo en varios sistemas de
  scoring. Ahora es `None` (desconocido), y el intento fallido se registra en
  la nueva columna `extras.hltb_checked` para no repetir la consulta en cada
  arranque. Se incluye una migración automática que reinterpreta los `0` ya
  guardados en la caché existente.
- `AvailableTimeScorer` ya no lanza `ZeroDivisionError` cuando el usuario
  introduce 0 horas disponibles.
- `MixedScore` ya no revienta con `AssertionError` ante pesos que la propia
  pantalla de configuración considera válidos (tolerancias desalineadas).
- `ConfigManager` ya no pierde los géneros preferidos del usuario en cada
  reinicio de la aplicación (filtrado incorrecto de campos con
  `default_factory`).
- `GenreFilter` filtraba de mentira: aceptaba todos los juegos sin excepción.
  Ahora filtra realmente por los géneros indicados.
- `TotalRatingSorter` trataba una puntuación de 0.0 como válida mientras sus
  sorters hermanos la trataban como ausente, dando ordenaciones contradictorias
  para los mismos datos. Unificado el criterio de "puntuación ausente" en
  `models/util.py:is_missing()`.
- `LibraryService.sort("mixed")` ignoraba los pesos y el contexto de scoring
  persistidos por el usuario, dando un orden distinto al de
  `LibraryService.score("mixed")` para la misma biblioteca.
- Resolución de Epic/Steam: cuando ningún candidato de IGDB superaba una
  similitud de título de 0.0, el selector devolvía `None` y la traza posterior
  lanzaba `AttributeError` en vez de degradar con gracia.
- `SteamUserCacher` no capturaba errores de SQLite (bloqueos, disco lleno),
  a diferencia del resto de cachers del proyecto.
- Un `TypeError` transitorio del cliente de IGDB se interpretaba como "el
  juego no existe", marcando juegos válidos como desconocidos para siempre.
- Un fallo de red en `SteamScoreEnricher` borraba las valoraciones de Steam
  ya conocidas en vez de conservarlas.
- El pipeline de enrichment se saltaba enrichers completos cuando el juego ya
  tenía *algún* campo en caché, dejando otros campos sin enriquecer para
  siempre.
- Ordenación: los juegos sin puntuación o sin duración podían acabar
  encabezando el ranking al ordenar de mayor a menor (`ScoredLibrary.sort`,
  `DurationSorter`) en vez de quedarse siempre al final.
- `LibraryRepository.load()` podía reventar con una ficha de caché sin nombre.

### Cambiado

- **Nueva versión: 1.1.0.**
- Los cuatro resolvers de tienda (Steam, GOG, Epic, Amazon) comparten ahora
  una plantilla común en `BaseResolver`; cada uno aporta solo su identificador
  y su estrategia de búsqueda contra IGDB, en vez de duplicar ~90% del flujo.
- Los seis cachers SQLite comparten una base común (`BaseCacher`): conexión
  reutilizada por hilo, esquema declarado una vez, migraciones idempotentes y
  manejo de errores uniforme, en vez de código copiado y ya divergente entre
  ellos.
- `load_library` ya no emite un `ThreadPoolExecutor` disfrazado de `Game` al
  final del generador (la GUI lo distinguía con
  `hasattr(item, 'duration_hours')`); ahora gestiona su propio pool de
  enrichment internamente.
- `LibraryRepository` reutiliza `IGMapperGame` para reconstruir juegos desde
  caché en vez de reimplementar la conversión de carátula, géneros y fecha.
- Los `Protocol` del core (`GameFilter`, `GameScorer`, etc.) lanzan
  `NotImplementedError` en su cuerpo por defecto en vez de `...`, para que un
  método sin implementar falle en voz alta en vez de devolver `None` en
  silencio.
- Documentación (`AGENTS.md`) actualizada con la convención del proyecto para
  valores ausentes (duración vs. puntuaciones) y con las instrucciones para
  ejecutar la suite de tests.

### Rendimiento

- `filter_library`/`add_games` eran cuadráticos (reconstruían la biblioteca
  entera por cada juego añadido): filtrar 2000 juegos pasa de ~62 ms a
  ~0.2 ms.
- `normalize_title` recompilaba 13 expresiones regulares en cada llamada, y
  se invoca una vez por cada `Game` construido: ~6x más rápido.
- Los cachers SQLite reutilizan la conexión por hilo y agrupan escrituras en
  una sola transacción en vez de abrir una conexión nueva (y nunca cerrarla)
  por cada operación: guardar 500 juegos pasa de ~77 ms a ~1.2 ms. Se añade
  `PRAGMA journal_mode=WAL` y `busy_timeout` para las escrituras concurrentes
  de los enrichers en segundo plano.
- `GenreScorer` reconstruía el conjunto de géneros en minúsculas por cada
  género de cada juego en vez de una vez por juego.

### Eliminado

- Código muerto: `CompositeGameScorer` (duplicaba `WeightedScore`, sin uso),
  `LibraryIndex` (nunca se instanciaba), y la función legacy
  `load_steam_library()`.

## [1.0.0] - 2026-05-23

- Primera versión estable. Interfaz TUI (Textual) funcional con
  multi-tienda (Steam, GOG, Epic, Amazon vía Heroic), enriquecimiento IGDB +
  HowLongToBeat + valoración Steam, 4 sistemas de scoring, filtros, flags de
  usuario y persistencia en SQLite.
- Documentación (`README.md`, capturas de pantalla) y renombrado del binario
  de build.
