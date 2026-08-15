"""
Llevarse todo Puntueitor en un zip, y traerlo de vuelta.

Hay cosas aquí dentro que NO se pueden regenerar: `library.sqlite` guarda qué
has terminado, ocultado, dejado pendiente o marcado como favorito, y eso no
está en ninguna API; `config.json` guarda las claves de IGDB y de Steam. El
resto —la biblioteca, los extras, las carátulas— se puede reconstruir, pero a
base de horas de red.

Mismo contrato que sus hermanos (`game_actions.py`, `library_refresh.py`):
nada de Textual ni de Panda3D, y los fallos salen como `BackupError` con un
mensaje ya presentable, porque quien llama lo único que va a hacer con él es
enseñarlo.

Dentro del zip, las cuatro carpetas de `core/paths.py` van bajo cuatro
prefijos fijos —`config/`, `data/`, `cache/`, `state/`— y no bajo sus rutas
reales: una copia hecha en una máquina tiene que poder restaurarse en otra
donde el usuario se llame distinto, o donde las XDG_* apunten a otro sitio.
"""
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from puntueitor.core import paths

logger = logging.getLogger(__name__)

#: Nombre con el que se propone guardar la copia.
BACKUP_NAME = "puntueitor.zip"

#: Cómo se llama el manifiesto y qué tiene que poner dentro. Es lo único que
#: distingue una copia nuestra de un zip cualquiera que el usuario tenga por
#: ahí, y restaurar sobrescribe sus datos: más vale negarse.
MANIFEST_NAME = "manifest.json"
MANIFEST_APP = "puntueitor"
MANIFEST_VERSION = 1

#: Qué carpeta va bajo qué prefijo. Las rutas se piden POR FUNCIÓN y no se
#: guardan resueltas, que es la regla de `core/paths.py`: resolviéndolas en
#: cada llamada, parchear las XDG_* o `Path.home` redirige de verdad, y es lo
#: que mantiene la suite de tests fuera de las carpetas del usuario.
ARCHIVE_DIRS = {
    "config": paths.config_dir,
    "data": paths.data_dir,
    "cache": paths.cache_dir,
    "state": paths.state_dir,
}

#: Bases de datos: se copian con la API de SQLite, no por bytes (ver
#: `_copy_database`).
_DATABASE_SUFFIXES = (".db", ".sqlite")

#: Los satélites del modo WAL. Ni se guardan ni se restauran, y los que haya
#: en el destino se borran al restaurar (ver `restore_backup`).
_SQLITE_SIDECARS = ("-wal", "-shm")


class BackupError(Exception):
    """Algo impidió hacer o restaurar la copia. El mensaje es para enseñarlo."""


@dataclass(frozen=True)
class BackupResult:
    path: Path
    files: int
    size: int

    @property
    def megabytes(self) -> float:
        return self.size / (1024 * 1024)


@dataclass(frozen=True)
class RestoreResult:
    files: int
    skipped: int = 0


def desktop_dir() -> Path:
    """
    El escritorio del usuario, o lo más parecido que se encuentre.

    Se mira primero `user-dirs.dirs`, que es donde el entorno guarda el
    nombre de verdad: en un sistema en español puede ser "Escritorio" y en
    uno en inglés "Desktop", y dar por hecho uno de los dos deja la ruta
    propuesta apuntando a una carpeta que no existe.

    Nunca falla: si no hay nada de eso, se propone el propio `$HOME`, que
    siempre existe y es un sitio razonable donde dejar un zip.
    """
    home = Path.home()
    config = home / ".config" / "user-dirs.dirs"
    try:
        for linea in config.read_text().splitlines():
            if not linea.startswith("XDG_DESKTOP_DIR"):
                continue
            valor = linea.split("=", 1)[1].strip().strip('"')
            ruta = Path(valor.replace("$HOME", str(home)))
            if ruta.is_dir():
                return ruta
    except OSError:
        pass

    for nombre in ("Desktop", "Escritorio"):
        if (home / nombre).is_dir():
            return home / nombre
    return home


def default_backup_path() -> Path:
    """La ruta que se propone en el cuadro de texto."""
    return desktop_dir() / BACKUP_NAME


# ──────────────────────────────
# Crear
# ──────────────────────────────


def _copy_database(source: Path, destination: Path) -> None:
    """
    Copia una base SQLite con su propia API, no por bytes.

    Importa, y mucho: las bases van en modo WAL y la aplicación que está
    haciendo la copia las tiene ABIERTAS. Copiar el `.db` con `shutil` deja
    fuera lo que todavía viva en el `-wal` —o sea, lo último que hizo el
    usuario— y puede dar directamente un fichero a medio escribir.
    `Connection.backup` lo resuelve: sincroniza y entrega un fichero ya
    consolidado, que además se puede guardar solo, sin satélites.
    """
    origen = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        copia = sqlite3.connect(destination)
        try:
            origen.backup(copia)
        finally:
            copia.close()
    finally:
        origen.close()


def _files_to_archive(directory: Path, prefix: str) -> list[tuple[Path, str]]:
    """Los ficheros de una carpeta con el nombre que llevarán en el zip."""
    if not directory.is_dir():
        return []
    return [
        (ruta, f"{prefix}/{ruta.relative_to(directory).as_posix()}")
        for ruta in sorted(directory.rglob("*"))
        if ruta.is_file() and not ruta.name.endswith(_SQLITE_SIDECARS)
    ]


def create_backup(destination: Path) -> BackupResult:
    """
    Escribe en `destination` un zip con las cuatro carpetas de Puntueitor.

    BLOQUEA un par de segundos con la biblioteca real (las carátulas son la
    mayor parte del peso).

    El zip se escribe a un temporal AL LADO del destino y solo al final se
    pone en su sitio con `os.replace`. Así, si se corta a la mitad, la copia
    anterior —que es justo la que se estaría a punto de necesitar— sigue
    intacta. Y al lado y no en /tmp porque `os.replace` tiene que ser atómico,
    y solo lo es dentro del mismo sistema de ficheros.

    Se comprime flojo (`compresslevel=1`) a propósito: casi todo el peso son
    carátulas JPEG, que ya vienen comprimidas, y apretar más solo cuesta
    segundos para ahorrar unos pocos kilobytes.
    """
    destination = Path(destination).expanduser()
    if destination.is_dir():
        destination = destination / BACKUP_NAME

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise BackupError(f"no se puede escribir en {destination.parent}: {error}")

    manifest = json.dumps({
        "app": MANIFEST_APP,
        "version": MANIFEST_VERSION,
        "created": datetime.now().isoformat(timespec="seconds"),
    }, indent=2)

    temporal = destination.with_name(destination.name + ".parcial")
    ficheros = 0
    try:
        with tempfile.TemporaryDirectory(prefix="puntueitor-backup-") as tmp:
            tmp = Path(tmp)
            with zipfile.ZipFile(
                temporal, "w", zipfile.ZIP_DEFLATED, compresslevel=1,
            ) as zf:
                zf.writestr(MANIFEST_NAME, manifest)
                for prefijo, carpeta in ARCHIVE_DIRS.items():
                    for ruta, nombre in _files_to_archive(carpeta(), prefijo):
                        if ruta.suffix in _DATABASE_SUFFIXES:
                            copia = tmp / ruta.name
                            _copy_database(ruta, copia)
                            zf.write(copia, nombre)
                        else:
                            zf.write(ruta, nombre)
                        ficheros += 1
        os.replace(temporal, destination)
    except (OSError, sqlite3.Error, zipfile.BadZipFile) as error:
        temporal.unlink(missing_ok=True)
        raise BackupError(f"no se pudo crear la copia: {error}")

    resultado = BackupResult(destination, ficheros, destination.stat().st_size)
    logger.info(
        f"copia de seguridad en {destination}: "
        f"{ficheros} ficheros, {resultado.megabytes:.1f} MB"
    )
    return resultado


# ──────────────────────────────
# Restaurar
# ──────────────────────────────


def _target_for(name: str) -> Path | None:
    """
    Dónde va una entrada del zip, o None si no va a ninguna parte.

    Aquí está la defensa contra los zips preparados. El destino son carpetas
    REALES del usuario, así que una entrada con `..` o con ruta absoluta
    escribiría donde le diera la gana del `$HOME` (zip-slip). Se acepta solo
    lo que cuelga de uno de los cuatro prefijos conocidos y no se sale de él;
    todo lo demás se descarta contado.
    """
    partes = Path(name).parts
    if len(partes) < 2:
        return None
    if partes[0] not in ARCHIVE_DIRS:
        return None
    if any(parte in ("..", "/") for parte in partes) or name.startswith("/"):
        return None

    base = ARCHIVE_DIRS[partes[0]]()
    destino = base.joinpath(*partes[1:])
    # Cinturón y tirantes: aunque lo de arriba ya lo impide, se comprueba que
    # la ruta resuelta sigue colgando de su carpeta.
    try:
        destino.resolve().relative_to(base.resolve())
    except ValueError:
        return None
    return destino


def _clear_sidecars(path: Path) -> None:
    """
    Borra los `-wal`/`-shm` que hubiera junto a una base recién restaurada.

    Un WAL de la base ANTERIOR al lado de una base restaurada es de las
    peores cosas que pueden quedar: SQLite lo aplicará encima creyendo que le
    pertenece, y lo que se acaba de recuperar sale revertido o corrupto.
    """
    for suffix in _SQLITE_SIDECARS:
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def _check_manifest(zf: zipfile.ZipFile) -> None:
    try:
        manifest = json.loads(zf.read(MANIFEST_NAME))
    except KeyError:
        raise BackupError("el zip no es una copia de Puntueitor")
    except (json.JSONDecodeError, OSError) as error:
        raise BackupError(f"la copia está dañada: {error}")

    if manifest.get("app") != MANIFEST_APP:
        raise BackupError("el zip no es una copia de Puntueitor")


def restore_backup(source: Path) -> RestoreResult:
    """
    Vuelca una copia sobre las carpetas del usuario, sobrescribiendo.

    Quien llame a esto tiene que haber preguntado antes: los datos actuales
    se pierden. Y después hay que CERRAR la aplicación, no seguir: las bases
    restauradas se han escrito por debajo de unas conexiones SQLite que
    siguen abiertas, y esas conexiones no se han enterado.

    Se comprueba el manifiesto antes de tocar nada, para que un zip que no
    sea nuestro no deje las carpetas a medio sobrescribir.
    """
    source = Path(source).expanduser()
    if not source.is_file():
        raise BackupError(f"no existe el fichero {source}")

    restaurados = 0
    descartados = 0
    try:
        with zipfile.ZipFile(source) as zf:
            _check_manifest(zf)

            for info in zf.infolist():
                if info.is_dir() or info.filename == MANIFEST_NAME:
                    continue
                destino = _target_for(info.filename)
                if destino is None:
                    logger.warning(f"copia: entrada descartada {info.filename!r}")
                    descartados += 1
                    continue

                destino.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as origen, open(destino, "wb") as salida:
                    shutil.copyfileobj(origen, salida)
                if destino.suffix in _DATABASE_SUFFIXES:
                    _clear_sidecars(destino)
                restaurados += 1
    except zipfile.BadZipFile as error:
        raise BackupError(f"la copia está dañada: {error}")
    except OSError as error:
        raise BackupError(f"no se pudo restaurar: {error}")

    logger.info(f"copia restaurada desde {source}: {restaurados} ficheros")
    return RestoreResult(restaurados, descartados)
