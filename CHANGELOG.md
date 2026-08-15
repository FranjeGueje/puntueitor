# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

## [2.0.0] - 2026-08-15

Puntueitor deja de ser una aplicación de terminal con una interfaz y pasa a
tener **dos**: la de siempre y un carrusel 3D pensado para jugar en el sofá,
con mando y sin teclado. Las dos comparten exactamente los mismos datos y los
mismos servicios; lo único que cambia es cómo se enseñan.

### ⚠️ Al actualizar desde 1.x

- **Los ficheros de datos se mueven solos** la primera vez que arranques.
  Estaban repartidos entre `~/.cache` y `~/.config`, y pasan a las rutas
  estándar XDG: los ajustes a `~/.config/puntueitor`, las bases de datos a
  `~/.local/share/puntueitor` y el log a `~/.local/state/puntueitor`. No se
  pierde nada y no hay que hacer nada; el traslado nunca sobrescribe.
  Lo importante es **por qué**: `puntueitor.db` guarda la relación de tus
  juegos con IGDB, que cuesta horas de red reconstruir, y vivía en `~/.cache`,
  un directorio cuyo contrato es justamente que se puede borrar.
- Las columnas nuevas de la base se añaden al vuelo. No hay que regenerar nada.
- Aun así, **haz una copia antes de actualizar**: ahora se hace desde la propia
  aplicación (`b` en la TUI, Opciones → Avanzado en el carrusel).

### Añadido

- **Carrusel 3D (`puntueitor.gui3d`), interfaz completa en Panda3D**: cajas de
  juego en un arco navegable, ficha del seleccionado, carátulas cargadas bajo
  demanda, etiquetas de estado sobre la caja (favorito, terminado, pendiente,
  nota y duración), fondo y tipografía propios.
- **Mando con hot-plug**, conectable y desconectable en caliente, con todas
  las acciones accesibles sin teclado. La cruceta se detecta por tres vías
  distintas porque ninguna funciona en todos los mandos.
- **Menús apilables** en el carrusel: opciones, configuración, scoring y sus
  ajustes, filtros, ordenación y el menú de cada juego.
- **Modo desconocidos** en el carrusel: los juegos que IGDB no ha sabido
  identificar, en cajas negras con su título, y la posibilidad de buscarlos a
  mano o de volver a intentarlo por tienda.
- **Copia de seguridad y restauración** en las dos interfaces: toda tu
  instalación en un zip —ajustes, las dos bases de datos y las carátulas— y de
  vuelta. Las bases se copian con la API de SQLite y no por bytes, porque
  están abiertas mientras se copian.
- **Enriquecer y desconocer un juego suelto**, sin tocar el resto de la
  biblioteca.
- **Actualizar y regenerar la biblioteca desde el carrusel**, con los juegos
  apareciendo según se resuelven.
- Salto rápido por grupos de la ordenación (L1/R1) y vuelta al principio del
  carrusel (L3 o la tecla Inicio).
- La suite de tests entra en el repositorio: **409 tests**, con aislamiento
  para todos.

### Cambiado

- **Nueva versión: 2.0.0.**
- `puntueitor.gui` pasa a llamarse **`puntueitor.tui`**, ahora que hay dos
  interfaces y "gui" ya no distingue nada.
- **Las tiendas desmarcadas dejan de verse** en las dos interfaces, y tampoco
  se consultan al actualizar. La configuración de tiendas vive en
  `~/.config` y afecta a las dos por igual.
- **El log explica los fallos en vez de enseñar excepciones**: distingue no
  tener internet de que las credenciales no valgan, avisa cuando una tienda
  está activa pero no se puede consultar, y termina cada carga con un resumen
  por tienda. Las dos interfaces escriben en el mismo fichero —el carrusel
  antes no dejaba ninguna línea— y el log rota en vez de borrarse al arrancar.
- Los ajustes de scoring se guardan en su propio `scoring.json`, aparte del
  fichero que tiene tus claves de API: es el que más se reescribe y el otro es
  el que más duele perder.
- El arranque del carrusel pasa de 5,9 s a 1,5 s cargando las carátulas bajo
  demanda.

### Corregido

- **Importar `core.paths` movía ficheros del `$HOME` real.** Como lo importa
  medio proyecto, bastaba con lanzar la suite de tests para que se manosearan
  los ficheros del usuario. Un módulo que se importa no debe tocar el disco.
- **Restaurar una copia se perdía al cerrar la aplicación**: los ficheros se
  escribían sobre el mismo inodo que SQLite tenía abierto, y las conexiones
  vivas volcaban su estado encima al cerrarse, dejando las bases con el
  esquema y ninguna fila. Ahora se escribe en un fichero nuevo.
- **Regenerar la biblioteca no vaciaba la base**: se borraba el fichero, pero
  los cachers mantienen una conexión abierta por hilo y seguían contestando
  desde el inodo huérfano, así que todo lo reconstruido acababa en un fichero
  fantasma. Ahora se vacían las tablas.
- Corrupción intermitente de carátulas en el carrusel.
- Al desconocer un juego se guardaba con el nombre que le da IGDB en vez del
  que tiene en su tienda, que es justo el que hace falta para reconocerlo.
- El cuadro de texto dejaba de aceptar teclas a los ~29 caracteres: no cabía
  ni un Client Secret de IGDB ni la ruta de Heroic.
- «Enriquecer todo» borraba los datos extra antes de empezar, así que
  interrumpirlo a la mitad dejaba sin duración ni notas a los juegos que no
  había dado tiempo a procesar. Ahora hay dos versiones y la que no borra es
  la primera.
- Y diez errores más encontrados en la revisión del core, más los propios del
  carrusel según se construía.

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
