"""
Rutas de la aplicación, siguiendo la especificación XDG Base Directory.

Un solo sitio donde vive la respuesta a "¿dónde va esto?", en vez de
`Path.home() / ".cache" / "puntueitor"` repetido por media docena de
módulos, que es como se llegó a tener datos irreemplazables guardados en un
directorio cuyo contrato es justamente que se puede borrar.

El reparto y el porqué de cada uno:

- `CONFIG_DIR` (~/.config): ajustes que el usuario podría editar a mano.
  Solo `config.json`.

- `DATA_DIR` (~/.local/share): datos del usuario y datos derivados CAROS de
  reconstruir. Aquí van las dos bases de datos:
    * `library.sqlite` — qué juegos has marcado como terminado, oculto,
      pendiente o favorito. No se puede regenerar de ninguna manera: si se
      pierde, se pierde y ya está.
    * `puntueitor.db` — contiene `resolvers`, que según la "Regla de Oro"
      del proyecto es la ÚNICA fuente de verdad de qué juegos hay en la
      biblioteca, y `extras`, que son horas de HowLongToBeat y puntuaciones
      de Steam: técnicamente regenerables, pero a base de miles de llamadas
      a API. Estaba en ~/.cache, donde cualquier limpiador de disco se lo
      podía llevar por delante y donde casi nadie hace copia de seguridad.

  Esa base de datos también lleva dentro la tabla `games`, que sí es caché
  pura de IGDB. Se queda ahí a propósito: separarla en otro fichero obliga a
  que todos los cachers manejen dos conexiones para ahorrar poco más de un
  megabyte que, como mucho, deja de purgarse solo.

- `CACHE_DIR` (~/.cache): lo que se puede borrar sin consecuencias, porque
  se vuelve a bajar solo — carátulas, el token de IGDB y la copia local de
  la biblioteca de Steam.

- `STATE_DIR` (~/.local/state): el log. No es configuración, no es caché y
  no es un dato que valga la pena guardar en copias.

Se respetan las variables de entorno XDG_*_HOME si están puestas.

Todo son FUNCIONES, no constantes de módulo, y eso importa: resolviéndolas
en cada llamada, parchear `Path.home` o las XDG_*_HOME redirige de verdad la
aplicación entera a un directorio temporal. Con constantes calculadas al
importar, ese parcheo no tiene ningún efecto — y no es teórico: la primera
versión de este módulo las tenía como constantes, los tests de configuración
seguían parcheando `Path.home` creyendo que estaban aislados, y al pasar la
suite sobrescribieron el config.json real del usuario y le borraron las
claves de API.

Por la misma razón, IMPORTAR ESTE MÓDULO NO TOCA EL DISCO. Ni crea
directorios ni mueve nada: la migración de rutas antiguas
(`migrate_legacy_paths`) hay que pedirla explícitamente desde el punto de
entrada de cada frontend. Antes se ejecutaba sola al importar, y como
importar esto lo hace medio proyecto, bastaba con arrancar `pytest` para que
se movieran ficheros del `$HOME` real antes de que ningún aislamiento
pudiera actuar.
"""
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "puntueitor"


def _xdg_dir(env_var: str, default: Path) -> Path:
    """Directorio base XDG, con su variable de entorno si está definida."""
    value = os.environ.get(env_var)
    return (Path(value) if value else default) / APP_NAME


def config_dir() -> Path:
    return _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config")


def data_dir() -> Path:
    return _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share")


def cache_dir() -> Path:
    return _xdg_dir("XDG_CACHE_HOME", Path.home() / ".cache")


def state_dir() -> Path:
    return _xdg_dir("XDG_STATE_HOME", Path.home() / ".local" / "state")


def config_file() -> Path:
    """Credenciales, tiendas activas y rutas. Se toca poco."""
    return config_dir() / "config.json"


def audio_dir() -> Path:
    """
    Música y efectos del carrusel 3D, que pone el usuario.

    En `CONFIG_DIR` y no en `DATA_DIR` porque es contenido suyo, que trae,
    cambia y quita a mano: la misma categoría que `config.json`, y en la
    carpeta de configuración lo encuentra sin tener que buscarlo. No se crea
    nunca desde aquí — si no existe, el frontend arranca en silencio.
    """
    return config_dir() / "audio"


def scoring_file() -> Path:
    """
    Ajustes de los sistemas de puntuación (pesos, horas, géneros).

    Aparte de `config_file()` a propósito: esto se reescribe cada vez que se
    toca un peso desde la interfaz, y el otro fichero guarda las claves de
    API. No conviene que el dato que más se escribe comparta fichero con el
    que más duele perder.
    """
    return config_dir() / "scoring.json"


def main_db() -> Path:
    """Biblioteca: `resolvers`, `extras`, `unknown_games` y la caché `games`."""
    return data_dir() / "puntueitor.db"


def library_db() -> Path:
    """Marcas del usuario: terminado, oculto, pendiente, favorito."""
    return data_dir() / "library.sqlite"


def covers_dir() -> Path:
    return cache_dir() / "covers"


def igdb_token_file() -> Path:
    return cache_dir() / "igdb_token.json"


def store_libraries_db() -> Path:
    """
    La última biblioteca que devolvió cada tienda por su API.

    En `CACHE_DIR` porque es exactamente eso: se rehace sola con un refresco.
    Lo que no se puede perder —tus notas, tus marcas— vive en otro sitio.
    """
    return cache_dir() / "store_libraries.sqlite"


def store_token_file(store: str) -> Path:
    """
    El token de sesión de una tienda (`gog`, `epic`, `amazon`).

    Junto al de IGDB y por el mismo motivo: si se pierde, lo único que pasa
    es que hay que volver a iniciar sesión.
    """
    return cache_dir() / f"{store}_token.json"


def log_file() -> Path:
    return state_dir() / "puntueitor.log"


def tui_state_file() -> Path:
    """
    Estado de la TUI recordado entre sesiones (hoy, solo los filtros de
    biblioteca; pensado para acoger cualquier otro ajuste de la TUI más
    adelante sin cambiar de fichero).

    En `STATE_DIR`, no en `CONFIG_DIR`: es estado que conviene que sobreviva
    a reinicios, pero no un ajuste que el usuario vaya a editar a mano ni le
    vaya a preocupar respaldar — la misma categoría que `log_file()`.

    Se llamó `filter_state.json` hasta que gui3d empezó a necesitar su
    propio fichero de estado (`gui3d_state_file()`): un nombre genérico deja
    claro de un vistazo a qué frontend pertenece cada uno.
    """
    return state_dir() / "tui.json"


def gui3d_state_file() -> Path:
    """
    Estado del frontend 3D recordado entre sesiones (filtros del carrusel
    hoy; sitio para más ajustes de gui3d más adelante). Hermano de
    `tui_state_file()`, uno por frontend — no comparten fichero porque sus
    modelos de filtrado son distintos (acumulativo por nombre en la TUI,
    tri-estado evaluado contra la biblioteca completa en gui3d).
    """
    return state_dir() / "gui3d.json"


def _legacy_moves() -> tuple[tuple[Path, Path], ...]:
    """(origen, destino) de la reorganización de directorios."""
    home = Path.home()
    return (
        (home / ".cache" / APP_NAME / "puntueitor.db", main_db()),
        (home / ".config" / APP_NAME / "library.sqlite", library_db()),
        (home / ".cache" / APP_NAME / "puntueitor.log", log_file()),
        (home / ".config" / APP_NAME / "filter_state.json", tui_state_file()),
    )

# SQLite en modo WAL (ver `base_cacher`) deja dos ficheros satélite junto al
# principal. Hay que moverlos con él: el -wal puede contener transacciones
# todavía no volcadas, así que llevarse solo el .db perdería lo último
# escrito, y dejar un -wal huérfano apuntando a otra base es peor aún.
_SQLITE_SIDECARS = ("-wal", "-shm")


def _move(source: Path, destination: Path) -> bool:
    """Mueve `source` a `destination` con sus satélites. True si movió algo."""
    if not source.exists() or destination.exists():
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))

    for suffix in _SQLITE_SIDECARS:
        sidecar = source.with_name(source.name + suffix)
        if sidecar.exists():
            shutil.move(str(sidecar), str(destination.with_name(destination.name + suffix)))
    return True


def migrate_legacy_paths() -> None:
    """
    Traslada los ficheros que estaban en la ubicación antigua.

    HAY QUE LLAMARLA A MANO, y como PRIMERA sentencia del punto de entrada
    de cada frontend (`gui/app.py` y `gui3d/app.py`, que son además los dos
    que empaqueta PyInstaller). Dos condiciones que cumplir al hacerlo:

    1. Antes de que nada abra una base de datos o un log. Si un cacher creara
       primero el fichero destino, `_move` lo vería ocupado, se saltaría el
       traslado, y el usuario se encontraría la biblioteca a cero con sus
       datos intactos pero huérfanos en la ruta vieja.
    2. Antes de configurar el logging, por lo mismo: `logging.basicConfig`
       con `filemode="w"` crea el log en el destino y dejaría el antiguo sin
       migrar.

    Durante mucho tiempo se llamaba sola al importar este módulo, que
    garantizaba (1) y (2) gratis. Se quitó porque el precio era inaceptable:
    importar `puntueitor.core.paths` —cosa que hace casi todo el proyecto,
    incluido `conftest.py` a través de `ConfigManager`— MOVÍA ficheros del
    `$HOME` real. En la suite de tests eso ocurría antes de que el fixture de
    aislamiento pudiera actuar, así que cada `pytest` manoseaba los ficheros
    reales del usuario. Un módulo que se importa no debe tocar el disco.

    Nunca borra nada ni sobrescribe: si el destino ya existe, no toca el
    origen. Y cualquier fallo se registra sin propagarse — que no se pueda
    migrar es un problema, pero tumbar el arranque por ello es peor.
    """
    for source, destination in _legacy_moves():
        try:
            if _move(source, destination):
                logger.info(f"Migrado {source} -> {destination}")
        except Exception as e:
            logger.warning(f"No se pudo migrar {source} a {destination}: {e}")
