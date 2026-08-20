# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

## [3.0.0] - 2026-08-20

Puntueitor deja de leer los ficheros de otros programas. Las tiendas ya no
salen de la caché en disco de Heroic ni de los `.vdf` de Steam, sino de **sus
propias APIs**, con sesión propia. Ya no hace falta tener Heroic instalado, ni
abrirlo para que refresque, ni acertar con su carpeta. Entra además **itch.io**
como quinta tienda, y el carrusel deja de ser mudo.

### ⚠️ Al actualizar

- **Hay que iniciar sesión** en GOG, Epic, Amazon e itch.io: Opciones →
  **Cuentas** (`a` en la TUI). Se abre el navegador, inicias sesión y pegas de
  vuelta la dirección. Steam no: sigue con su API key y su Steam ID.
- El ajuste `heroic_path` desaparece. Si sigue en tu `config.json` se ignora y
  se dice en el log.
- Nada de la biblioteca se pierde: tus marcas, notas y desconocidos siguen
  donde estaban. La primera carga tras iniciar sesión vuelve a preguntar a cada
  tienda.
- **La biblioteca de Epic crecerá**: vuelven los DLC y las aplicaciones (de 451
  entradas a 495 en una biblioteca real). Los que IGDB no reconozca irán a
  Desconocidos, así que esa lista también crece.

### Añadido

- **Bibliotecas por API, tienda a tienda.** Steam por
  `IPlayerService/GetOwnedGames`; GOG por la API del cliente Galaxy; Epic por
  las del Epic Games Launcher; Amazon por su servicio de *entitlements*. Las
  tres últimas son las mismas que usan gogdl, Legendary y Nile, o sea las que
  ya había debajo de Heroic — solo que ahora la sesión es nuestra.
- **itch.io, quinta tienda**, por la *Owned Keys API Route* con el permiso
  `profile:owned`: la única de las cinco con una API oficial y documentada por
  la propia tienda. Precisamente por eso no hay ningún cliente ajeno cuyo
  `client_id` reutilizar, así que pide **un paso más, una sola vez**: registrar
  una aplicación en `itch.io/user/settings/oauth-apps` y pegar su Client ID en
  Cuentas. Si falta, el inicio de sesión lo dice y explica dónde conseguirlo.
- **Funciona sin conexión.** La última biblioteca de cada tienda queda
  guardada. Si no hay red, si la sesión ha caducado o si la tienda contesta
  cero juegos, se sirven los juegos de la última vez y se explica en el log, en
  vez de dejar la biblioteca vacía sin decir por qué.
- **Menú de Cuentas** en las dos interfaces: las credenciales de IGDB y Steam,
  y el estado de las sesiones de cada tienda. Acepta la dirección entera, el
  texto que enseña Epic o el código a secas, para no obligar a nadie a buscar
  un parámetro dentro de una URL de cuatrocientos caracteres.
- **Pegar en el carrusel 3D**, con `Ctrl+V` o el botón **X** del mando. Sin
  esto había que teclear esa dirección a mano, con un mando y desde el sofá.
  Panda3D no expone el portapapeles, así que se pregunta al sistema:
  `wl-paste`, `xclip`, `xsel` y, si no hay ninguno, **Klipper por D-Bus**, que
  es lo que hace que funcione en KDE Plasma sin instalar nada.
- **Sonido en el carrusel**: música de fondo en bucle y tres efectos —aceptar,
  volver y mover el foco—, con volumen independiente para música y efectos.
  **El audio no viene incluido**: se lee de `~/.config/puntueitor/audio/`
  (`music.ogg`, `accept.wav`, `back.wav`, `move.wav`; las dos extensiones valen
  para cualquiera). Sin esa carpeta suena lo de antes, o sea nada, y se dice en
  el log; así no hay que meter en el repositorio material de terceros con su
  licencia detrás. Un botón, un sonido, y solo si hace algo: pulsar A sobre un
  valor que se cambia con izquierda/derecha sigue callado, porque un clic sin
  efecto se lee como que la aplicación se ha colgado.
- **Un registro de tiendas** (`core/stores/`): cada tienda declara en su módulo
  todo lo suyo —etiqueta, color, bandera de configuración, proveedor, resolver,
  sesión y qué se le pide pegar al usuario— y el resto del programa lo lee de
  ahí. Antes ese mismo dato vivía en once ficheros sincronizados a mano, y eso
  ya había fallado dos veces. Añadir una tienda pasa a ser escribir su módulo,
  más dos líneas que no pueden vivir en él: su miembro del enum `Stores` y su
  campo en `Config`. Hay tests que comprueban que no se olvidan.
- Los tokens se guardan en `~/.cache/puntueitor/`, solo legibles por ti, y se
  renuevan solos.
- Los créditos del carrusel nombran a **legendary, gogdl y nile**, que son
  quienes averiguaron y publicaron las APIs de Epic, GOG y Amazon. No usamos su
  código y su licencia no obliga a nada; se les nombra porque sin ellos tres de
  las cinco tiendas no funcionarían.
- `tools/entorno-prueba.sh`: arranca la aplicación contra un directorio aparte
  para poder probar sin tocar tus datos.

### Cambiado

- **La configuración se parte en dos menús.** Lo que era "Configuración" pasa a
  ser **Cuentas** (con qué te identificas) y **Tiendas** (cuáles se cargan).
- **Se acabó el "Guardar" en Opciones (carrusel 3D).** Cuentas, Tiendas y
  Puntueitor3D guardan cada ajuste en cuanto lo terminas de tocar. La fila
  "Guardar" no solo añadía un paso, es que **cerraba el menú**: escribir el
  Client ID de itch.io obligaba a guardar, salir de Cuentas y volver a entrar
  para llegar a la fila de "itch.io" que estaba dos líneas más abajo del campo
  recién rellenado. A cambio, **B en esos tres menús ya no descarta, solo
  cierra**. Los formularios de puntuación siguen editándose sobre una copia, y
  son el único sitio que lo hace: repartir tres porcentajes obliga a pasar por
  totales que no suman 100.
- **Recargar es mucho más rápido.** Medido sobre una biblioteca real de 1.336
  juegos: de 31,3 s de red a unos 4 s, que es lo que tarda la tienda más lenta
  ahora que van en paralelo. Epic no vuelve a preguntar por juegos que ya
  conoce (22,6 s → 1,9 s) y las páginas de GOG también van a la vez.
- **Vuelven los DLC y las aplicaciones de Epic**, como en la 2.x: se
  descartaban antes de llegar al identificador, así que no aparecían ni en la
  biblioteca ni en Desconocidos.
- `core/providers/` es la capa nueva: cada tienda sabe pedirse a sí misma y el
  pipeline solo recorre proveedores. Antes la obtención de datos vivía dentro
  de `load_library` y sabía de ficheros y de HTTP a la vez.
- Los enriquecedores se construyen en un solo sitio
  (`core/enrichers/factory.py`), y los textos de los sistemas de puntuación
  viven en `core/scoring/catalog.py` en vez de estar escritos una vez por
  interfaz. El cliente de la API de Steam deja de ser un paquete aparte
  (`steampy/`) y pasa a `core/raw/`, junto al de HowLongToBeat.
- `gui3d/app.py` se reparte en módulos —copias de seguridad, scoring, Cuentas y
  Tiendas, Editor Rápido— y baja de las 3.000 líneas. Al escribir los tests de
  scoring apareció un bug real: el catálogo había renombrado `config` a
  `config_form` y cinco sitios seguían con el nombre viejo, así que el
  formulario de configurar un sistema (tecla X) se habría roto.
- El aviso de "Steam no devolvió ningún juego" ya no manda a mirar primero la
  privacidad del perfil: con la clave y el ID de la misma cuenta la privacidad
  no se aplica, así que lo probable es otra cosa.

### Corregido

- **Las duraciones de HowLongToBeat se perdían.** Al acertar, el enriquecedor
  devolvía el dato pero no lo guardaba —solo se persistían los fallos—, así que
  los mismos juegos se consultaban en cada recarga y se perdían al cerrar.
  Igual con las notas de Steam, que además se guardaban solo en uno de los seis
  caminos que llevaban a ellas.
- **El carrusel se caía al pintar una caja de itch.io.** El banner del estuche
  tenía las abreviaturas en una tabla escrita a mano con las cuatro tiendas de
  antes, así que la quinta reventaba con un `KeyError`. Ahora la declara cada
  tienda en el registro. El guardián que impide escribir listas de tiendas a
  mano **no veía esa tabla** —mira línea a línea buscando cadenas literales—,
  así que se añade la comprobación que faltaba.
- **Reintentar un desconocido de itch.io usaba el resolver de GOG.** El
  despacho tenía un `else` que mandaba allí todo lo que no fuera Steam ni Epic,
  así que el juego se buscaba por la fuente externa equivocada y, de encajar
  algo por título, se habría guardado como juego de GOG. La suite pasaba con el
  fallo dentro porque nadie probaba esa función.
- **Los juegos de ejemplo no se iban.** Al recargar los reales se añadían
  encima y quedaban los seis mezclados hasta reiniciar. Y marcar uno dejaba una
  fila huérfana en `library.sqlite`, que es la única base que no se puede
  regenerar.
- **La tecla `e` de la terminal actualiza también lo que ya se sabía**, como su
  equivalente del carrusel; y un juego que falle al enriquecer ya no tumba el
  lote entero en la TUI.
- Un corte de internet renovando una sesión ya no se confunde con una sesión
  caducada: antes, un rato sin red habría obligado a volver a entrar en todas
  las tiendas.
- Varios avisos mandaban a "Opciones → Configuración" para arreglar
  credenciales que ya no están ahí. Son justo los que se leen cuando algo no
  funciona, así que ahora cada uno manda al menú que toca.

### Notas de diseño

- **En itch.io se pega la dirección, igual que en las otras.** Admitiría un
  `redirect_uri` a `localhost` y capturar la vuelta automáticamente, pero sería
  la única tienda que se comporta distinto: un gesto que aprender en vez de
  cinco pantallas iguales. Cuando eso pueda hacerse en todas, bastará con
  cambiar un módulo.
- **Su token no caduca ni trae `refresh_token`** (concesión implícita), así que
  se guarda con una caducidad ficticia de 30 días y, al cumplirse, se revalida
  pidiendo la primera página de la biblioteca. Contra la biblioteca y no contra
  `/profile`, que exige el permiso `profile:me` y contestaba 403 con un token
  bueno. De paso, eso detecta una sesión revocada desde itch.io.
- **Se resuelve por id, no solo por título**: IGDB indexa itch.io como fuente
  externa (nº 30), comprobado contra la API real antes de escribir el resolver.
  Aun así queda la búsqueda por título de reserva, porque itch.io tiene cientos
  de miles de juegos y IGDB no los tiene todos.

### Eliminado

- `core/heroics/`: la lectura de `gog_library.json`, `legendary_library.json` y
  `nile_library.json`.
- `steampy/core/`: el lector de los `.vdf` de Steam. Era código muerto y además
  dependía de un paquete que ni siquiera estaba en `requirements.txt`.
- El ajuste `heroic_path` y su campo en las dos interfaces.

---

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
- **Editor Rápido** en el carrusel (`R3` o `e`): las cuatro direcciones del
  stick derecho marcan y desmarcan terminado, pendiente, oculto y favorito del
  juego seleccionado sin abrir ningún menú. Es lo que la TUI hace con
  `F1`/`F2`/`F3`, y lo que faltaba para poder repasar la biblioteca con el
  mando en la mano.
- **Pantalla de créditos** (Opciones → Créditos), con la atribución de los
  iconos y las tipografías que exigen sus licencias.
- **Enriquecer y desconocer un juego suelto**, sin tocar el resto de la
  biblioteca.
- **Actualizar y regenerar la biblioteca desde el carrusel**, con los juegos
  apareciendo según se resuelven.
- Salto rápido por grupos de la ordenación (L1/R1) y vuelta al principio del
  carrusel (L3 o la tecla Inicio).
- La suite de tests entra en el repositorio: **440 tests**, con aislamiento
  para todos, y se ejecutan en cada push (GitHub Actions).

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
- El menú **Avanzado** se parte en dos secciones, DATOS y COPIA DE SEGURIDAD,
  y **«Regenerar todo» pasa a llamarse «Restaurar Puntueitor MUY
  DESTRUCTIVO»**. Se apunta porque es el nombre de una acción que borra la
  base de datos entera: quien lo conozca por su nombre viejo tiene que poder
  atar cabos.

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
- **El stick derecho rebotaba**: un solo empujón marcaba y desmarcaba el
  estado varias veces seguidas, porque con un único umbral cada temblor del
  eje alrededor de él contaba como un gesto nuevo. Ahora lleva histéresis, la
  misma que ya tenían los gatillos.
- La navegación del carrusel iba demasiado rápida —8 juegos por segundo de
  salida y hasta 22— y pasarse del que buscabas era lo normal. Se ha bajado a
  la mitad; para cruzar la biblioteca están L1/R1 y L3.
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
