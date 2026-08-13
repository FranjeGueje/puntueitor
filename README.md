<p align="center">
  <img src="https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white" alt="Python 3.14">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/plataforma-linux-lightgrey" alt="Linux">
  <img src="https://img.shields.io/badge/versión-1.1.0-orange" alt="Version 1.1.0">
</p>

<h1 align="center">🎮 Puntueitor</h1>

<p align="center">
  <b>Centraliza, gestiona y optimiza la elección de tus próximas partidas basándose en tus bibliotecas actuales</b><br>
  Unifica Steam, GOG, Epic Games y Amazon en una sola interfaz TUI.<br>
  Enriquecimiento automático, filtros, puntuación multi-criterio y persistencia.
</p>

---

## 📸 Capturas

<p align="center">
  <i>Biblioteca principal con lista de juegos, detalle y barra de estado</i><br>
  <img src="docs/screenshots/main.png" alt="Vista principal" width="800">
</p>

<p align="center">
  <i>Diálogo de puntuación con previsualización</i><br>
  <img src="docs/screenshots/puntualizador.png" alt="Puntuación" width="600">
</p>

<p align="center">
  <i>Biblioteca recomendada por Puntueitor</i><br>
  <img src="docs/screenshots/scoring.png" alt="Puntuación" width="600">
</p>

<p align="center">
  <i>Configuración de tiendas y credenciales</i><br>
  <img src="docs/screenshots/config.png" alt="Configuración" width="600">
</p>

---

## ✨ Características

| Característica | Detalle |
|---|---|
| **Multi-tienda** | Steam, GOG, Epic Games y Amazon (via Heroic Games Launcher) |
| **Enriquecimiento IGDB** | Carátula, género, puntuación de crítica, storyline, fecha de lanzamiento |
| **Duración** | HowLongToBeat — búsqueda automática por similitud de título |
| **Valoración Steam** | Puntuación SteamDB bayesiana + recuento de reseñas positivas/negativas |
| **Sistemas de scoring** | Mixto (critic + user + duración), Ponderado, Tiempo Disponible, Género |
| **Filtros** | Nombre, duración máxima, flags de usuario |
| **Flags de usuario** | Terminado, Backlog, Favorito, Oculto — persistidos en SQLite |
| **Ordenación** | Por nombre, puntuación usuario, crítica, mixta, duración (asc/desc) |
| **Juegos desconocidos** | Los juegos no encontrados en IGDB se aíslan para resolución manual |
| **Resolución IGDB** | Búsqueda por título con 15 resultados, o re-resolución automática por tienda |
| **Persistencia de filtros** | Los filtros activos se guardan entre sesiones (JSON) |
| **Caché unificada** | Una sola base de datos SQLite en `~/.local/share/puntueitor/` |
| **Binario único** | PyInstaller — sin dependencias del sistema, 25 MB |

---

## 🚀 Instalación

### Binario precompilado (Linux x86_64)

Descarga la última versión desde [Releases](https://github.com/FranjeGueje/puntueitor/releases):

```bash
chmod +x puntueitor-1.1.0-x86_64-linux
./puntueitor-1.1.0-x86_64-linux
```

### Desde fuente

```bash
git clone https://github.com/FranjeGueje/puntueitor.git
cd puntueitor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m puntueitor.tui.app
```

### Interfaz 3D

Además de la TUI hay un frontend 3D: un carrusel de cajas de juego con la
ficha del seleccionado, navegable con teclado o con mando.

```bash
python -m puntueitor.gui3d.app
```

Lee la misma biblioteca cacheada que la TUI y no modifica nada: lo único
que descarga son las carátulas que falten, y en segundo plano según vas
navegando. Necesita una GPU con OpenGL.

---

## ⚙️ Configuración

Al arrancar por primera vez, pulsa `c` para abrir el diálogo de configuración, o edita manualmente `~/.config/puntueitor/config.json`:

> Puntueitor sigue la especificación XDG Base Directory. Si vienes de una
> versión anterior, tus ficheros se trasladan solos al arrancar:
>
> | Directorio | Contenido |
> |---|---|
> | `~/.config/puntueitor/` | `config.json` |
> | `~/.local/share/puntueitor/` | biblioteca y marcas de usuario (`puntueitor.db`, `library.sqlite`) |
> | `~/.cache/puntueitor/` | carátulas y datos re-descargables |
> | `~/.local/state/puntueitor/` | log |
>
> La biblioteca ya no vive en `~/.cache`: ahí un limpiador de disco podía
> borrarla, y casi nadie incluye esa carpeta en sus copias de seguridad.

| Campo | Tipo | Descripción |
|---|---|---|
| `steam_api_key` | `string` | API Key de Steam (https://steamcommunity.com/dev/apikey) |
| `steam_user_id` | `int` | Tu Steam ID numérica (SteamID64) |
| `igdb_client_id` | `string` | Client ID de Twitch/IGDB (https://dev.twitch.tv/console) |
| `igdb_client_secret` | `string` | Client Secret de Twitch/IGDB |
| `steam_is_active` | `bool` | Cargar juegos de Steam |
| `gog_is_active` | `bool` | Cargar juegos de GOG (via Heroic) |
| `epic_is_active` | `bool` | Cargar juegos de Epic (via Heroic) |
| `amazon_is_active` | `bool` | Cargar juegos de Amazon (via Heroic) |
| `heroic_path` | `string` | Ruta a la carpeta de Heroic (vacío = auto-detectar) |
| `scoring_*` | `float/list` | Pesos de puntuación y géneros preferidos |

---

## ⌨️ Controles

| Tecla | Acción | Descripción |
|---|---|---|
| `p` | **Puntueitor** | Abre selector de sistema de puntuación |
| `c` | **Configurar** | Diálogo de configuración de API keys y tiendas |
| `o` | **Ocultos** | Alterna visibilidad de juegos marcados como ocultos |
| `s` | **Ordenar** | Diálogo de ordenación (nombre, puntuación, duración…) |
| `f` | **Filtrar** | Diálogo de filtros (nombre, duración, flags…) |
| `e` | **Enriquecedores** | Ejecuta HLTB + Steam Score en toda la biblioteca |
| `E` | **Regenerar** | Limpia caché de enriquecedores y vuelve a ejecutar |
| `u` | **Desconocidos** | Alterna vista de juegos desconocidos / biblioteca |
| `r` | **Actualizar** | Recarga tiendas desde API (juegos nuevos) |
| `R` | **Regenerar TODO** | Borra toda la caché SQLite y recarga desde cero |
| `F1` | **Terminado** | Marca/desmarca el juego seleccionado como terminado |
| `F2` | **Backlog** | Marca/desmarca el juego seleccionado como backlog |
| `F3` | **Favorito** | Marca/desmarca el juego seleccionado como favorito |
| `v` | **Carátula** | Abre la carátula del juego en el visor de imágenes del sistema |
| `q` | **Salir** | Cierra la aplicación |

### En diálogos modales

| Tecla | Acción |
|---|---|
| `↑`/`↓` | Navegar entre opciones |
| `Enter` | Seleccionar / Aceptar |
| `Escape` | Cancelar / Volver |
| `Letra` resaltada | Atajo directo a la opción (mayúscula = descendente) |

---

## 🏗️ Arquitectura

```
                    ┌─────────────┐
                    │  Textual UI  │
                    │  (app, screens, widgets)
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │     LibraryService       │
              │  (fachada de operaciones)│
              └────────────┬────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────┴────┐      ┌─────┴─────┐      ┌─────┴─────┐
   │ Filters │      │  Scoring   │      │ Repository │
   │ 7 clases│      │ 4 sistemas │      │ (SQLite)   │
   └─────────┘      └─────┬─────┘      └────────────┘
                          │
              ┌───────────┴───────────┐
              │      Enrichers         │
              │  (HLTB + Steam Score)  │
              └───────────────────────┘

              ┌───────────────────────┐
              │       Cachers          │
              │ (IGDB, Extras, Steam…) │
              └───────────────────────┘

    Resolvers → Mappers → Selectors → Pipeline → Models
```

### Flujo de datos

1. **Resolvers** obtienen datos crudos de Steam API, Heroic (GOG/Epic/Amazon), IGDB y HLTB
2. **Mappers** transforman los datos crudos en objetos `Game` canónicos
3. **Filters** aplican criterios (nombre, duración, flags…) sobre la biblioteca
4. **Scoring** calcula puntuaciones multi-criterio personalizadas
5. **Selectors** desambiguan entre candidatos duplicados de distintas tiendas
6. **Enrichers** añaden metadatos (duración HLTB, puntuación SteamDB)
7. **Pipeline** orquesta todo el flujo de carga, filtrado y enrichment

Para el diseño del sistema y el porqué de sus decisiones, ver
[`arquitectura.md`](arquitectura.md). Para notas de trabajo y trampas
concretas encontradas por el camino, [`AGENTS.md`](AGENTS.md).

---

## 🧪 Tests

```bash
source .venv/bin/activate
python -m pytest tests/
```

238 tests (unitarios + integración) que cubren:
- Modelos de dominio (Game, Library, ScoredLibrary)
- Filtros (7 clases)
- Scoring (helpers, atómicos, mixto, ponderado, tiempo disponible, género)
- Selectores, Mappers, Enrichers
- Resolvers (plantilla común y las 4 tiendas)
- Pipeline (scoring_ops, filter_library, enrichment)
- Servicios, Cachers (5 tipos), Config, Repository

---

## 📦 Build

Genera un binario único auto-contenido:

```bash
./build.sh
# → dist/puntueitor-1.1.0-x86_64-linux  (25 MB)
```

El nombre incluye versión, arquitectura y sistema automáticamente.

---

## 📄 Licencia

MIT © 2026 FranjeGueje. Ver [`LICENSE`](LICENSE).
