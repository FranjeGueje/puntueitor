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
    return config_dir() / "config.json"


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


def log_file() -> Path:
    return state_dir() / "puntueitor.log"


def _legacy_moves() -> tuple[tuple[Path, Path], ...]:
    """(origen, destino) de la reorganización de directorios."""
    home = Path.home()
    return (
        (home / ".cache" / APP_NAME / "puntueitor.db", main_db()),
        (home / ".config" / APP_NAME / "library.sqlite", library_db()),
        (home / ".cache" / APP_NAME / "puntueitor.log", log_file()),
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

    Se ejecuta al importar este módulo, y ese detalle es justo lo que la
    hace segura: cualquier código que vaya a abrir una base de datos tiene
    que pedirle antes la ruta a este módulo. Si se llamara más tarde, un
    cacher podría haber creado ya una base vacía en el destino, la migración
    vería el destino ocupado, se saltaría el traslado, y el usuario se
    encontraría la biblioteca a cero con sus datos intactos pero huérfanos
    en la ruta vieja.

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


migrate_legacy_paths()
