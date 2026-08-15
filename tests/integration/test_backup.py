"""
La copia de seguridad y su restauración.

En `integration` porque el sentido de esto es lo que queda escrito en disco:
un zip con las cuatro carpetas y, al revés, esas carpetas repobladas.

TODO ocurre dentro del sandbox de `conftest.py` (XDG_* y `Path.home` a un
temporal, comprobado además en `pytest_configure`). Aun así, cada test que va
a escribir comprueba primero que las rutas cuelgan de `tmp_path`: es barato, y
es justo el fallo que aquí no se puede permitir — restaurar SOBRESCRIBE, y una
fuga se llevaría por delante los ficheros de verdad del usuario.
"""
import json
import sqlite3
import zipfile

import pytest

from puntueitor.core import paths
from puntueitor.core.services.backup import (
    ARCHIVE_DIRS,
    MANIFEST_NAME,
    BackupError,
    create_backup,
    default_backup_path,
    desktop_dir,
    restore_backup,
)


@pytest.fixture(autouse=True)
def sin_fugas(tmp_path):
    """Ninguna de las cuatro carpetas puede salirse del temporal del test."""
    for nombre, carpeta in ARCHIVE_DIRS.items():
        ruta = carpeta()
        assert str(ruta).startswith(str(tmp_path)), f"FUGA en {nombre}: {ruta}"


@pytest.fixture
def poblado(tmp_path):
    """Las cuatro carpetas con algo que perder en cada una."""
    paths.config_dir().mkdir(parents=True, exist_ok=True)
    paths.config_file().write_text('{"igdb_client_id": "secreto"}')

    paths.data_dir().mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(paths.library_db())
    con.execute("CREATE TABLE estados (igdb_id INTEGER, finished INTEGER)")
    con.execute("INSERT INTO estados VALUES (1, 1)")
    con.commit()
    con.close()

    paths.covers_dir().mkdir(parents=True, exist_ok=True)
    (paths.covers_dir() / "1.jpg").write_bytes(b"\xff\xd8caratula")

    paths.state_dir().mkdir(parents=True, exist_ok=True)
    paths.gui3d_state_file().write_text('{"filtros": "algo"}')

    return tmp_path / "copia.zip"


def _vaciar() -> None:
    """Borra las cuatro carpetas, como si fuera una máquina nueva."""
    import shutil
    for carpeta in ARCHIVE_DIRS.values():
        shutil.rmtree(carpeta(), ignore_errors=True)


class TestIdaYVuelta:
    def test_restores_everything(self, poblado):
        create_backup(poblado)
        _vaciar()
        assert not paths.config_file().exists()

        resultado = restore_backup(poblado)

        assert resultado.files == 4
        assert "secreto" in paths.config_file().read_text()
        assert (paths.covers_dir() / "1.jpg").read_bytes() == b"\xff\xd8caratula"
        assert json.loads(paths.gui3d_state_file().read_text()) == {"filtros": "algo"}

    def test_user_states_survive(self, poblado):
        """
        Lo irrecuperable: terminado, oculto, pendiente y favorito no están en
        ninguna API. Si esto no vuelve, la copia no sirve para nada.
        """
        create_backup(poblado)
        _vaciar()

        restore_backup(poblado)

        con = sqlite3.connect(paths.library_db())
        assert con.execute("SELECT finished FROM estados").fetchone() == (1,)
        con.close()

    def test_the_zip_has_the_four_prefixes(self, poblado):
        create_backup(poblado)

        with zipfile.ZipFile(poblado) as zf:
            nombres = zf.namelist()
        assert MANIFEST_NAME in nombres
        assert "config/config.json" in nombres
        assert "data/library.sqlite" in nombres
        assert "cache/covers/1.jpg" in nombres
        assert "state/gui3d.json" in nombres

    def test_covers_are_included(self, poblado):
        """Se decidió meterlas: restaurar deja la biblioteca ya con imágenes."""
        create_backup(poblado)
        with zipfile.ZipFile(poblado) as zf:
            assert any(n.startswith("cache/covers/") for n in zf.namelist())


class TestBasesDeDatos:
    def test_copies_what_is_still_in_the_wal(self, poblado):
        """
        La razón de copiar con la API de SQLite y no con `shutil`.

        Se escribe en modo WAL y NO se cierra la conexión: ese último dato
        vive todavía en el `-wal`, así que una copia byte a byte del `.db` se
        lo dejaría fuera — y es justo lo último que hizo el usuario.
        """
        con = sqlite3.connect(paths.library_db())
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("INSERT INTO estados VALUES (99, 1)")
        con.commit()

        try:
            create_backup(poblado)
        finally:
            con.close()

        _vaciar()
        restore_backup(poblado)
        con = sqlite3.connect(paths.library_db())
        filas = con.execute("SELECT igdb_id FROM estados ORDER BY igdb_id").fetchall()
        con.close()
        assert (99,) in filas

    def test_sidecars_are_not_archived(self, poblado):
        """El `backup()` deja un fichero consolidado: no hacen falta."""
        paths.library_db().with_name("library.sqlite-wal").write_bytes(b"basura")

        create_backup(poblado)

        with zipfile.ZipFile(poblado) as zf:
            assert not any("-wal" in n or "-shm" in n for n in zf.namelist())

    def test_restoring_removes_a_stale_wal(self, poblado):
        """
        Un WAL de la base ANTERIOR junto a la restaurada es de lo peor que
        puede quedar: SQLite lo aplicaría encima creyéndolo suyo.
        """
        create_backup(poblado)
        paths.library_db().with_name("library.sqlite-wal").write_bytes(b"viejo")

        restore_backup(poblado)

        assert not paths.library_db().with_name("library.sqlite-wal").exists()


class TestRestaurarConLaAplicacionAbierta:
    """
    El fallo que se llevó por delante la biblioteca del usuario.

    Restaurar desde dentro de la aplicación significa escribir encima de unos
    ficheros que SQLite tiene ABIERTOS. Con un `open(destino, "wb")` se trunca
    el fichero sobre el MISMO inodo que tienen esas conexiones: al cerrarse
    después vuelcan su estado encima y lo restaurado desaparece. Se quedó el
    esquema y cero filas, y el carrusel —que cae a los juegos de muestra con
    la biblioteca vacía— parecía "mockeado".
    """

    def test_an_open_connection_cannot_undo_the_restore(self, poblado):
        create_backup(poblado)

        # Se vacía la base COMO SI la aplicación siguiera trabajando: en modo
        # WAL —el que usan los cachers— y con la conexión ABIERTA, que es la
        # parte que importa. Al cerrarla, SQLite consolida su WAL sobre el
        # fichero, y ahí es donde se perdía lo restaurado.
        viva = sqlite3.connect(paths.library_db())
        viva.execute("PRAGMA journal_mode=WAL")
        viva.execute("DELETE FROM estados")
        viva.commit()

        restore_backup(poblado)
        # ...y ahora la aplicación se cierra.
        viva.close()

        con = sqlite3.connect(paths.library_db())
        assert con.execute("SELECT COUNT(*) FROM estados").fetchone() == (1,)
        con.close()

    def test_restoring_makes_a_new_file(self, poblado):
        """
        La propiedad de la que depende lo anterior: se escribe en un inodo
        NUEVO, no en el que ya estaba. Quien tuviera el viejo abierto se queda
        con un huérfano y no puede tocar lo restaurado.
        """
        create_backup(poblado)
        antes = paths.library_db().stat().st_ino

        restore_backup(poblado)

        assert paths.library_db().stat().st_ino != antes

    def test_no_leftovers(self, poblado):
        """El temporal de cada fichero no puede quedarse por ahí."""
        create_backup(poblado)
        restore_backup(poblado)

        sobras = [
            p.name for p in paths.data_dir().iterdir()
            if ".restaurando" in p.name
        ]
        assert sobras == []


class TestZipsQueNoSonNuestros:
    def test_without_manifest(self, tmp_path):
        ajeno = tmp_path / "ajeno.zip"
        with zipfile.ZipFile(ajeno, "w") as zf:
            zf.writestr("config/config.json", "{}")

        with pytest.raises(BackupError, match="no es una copia"):
            restore_backup(ajeno)

    def test_with_another_apps_manifest(self, tmp_path):
        ajeno = tmp_path / "ajeno.zip"
        with zipfile.ZipFile(ajeno, "w") as zf:
            zf.writestr(MANIFEST_NAME, '{"app": "otra-cosa"}')

        with pytest.raises(BackupError, match="no es una copia"):
            restore_backup(ajeno)

    def test_nothing_is_written_before_checking(self, tmp_path):
        """El manifiesto se mira ANTES de tocar nada: ni a medias."""
        ajeno = tmp_path / "ajeno.zip"
        with zipfile.ZipFile(ajeno, "w") as zf:
            zf.writestr("config/config.json", "PISADO")

        with pytest.raises(BackupError):
            restore_backup(ajeno)
        assert not paths.config_file().exists()

    def test_missing_file(self, tmp_path):
        with pytest.raises(BackupError, match="no existe"):
            restore_backup(tmp_path / "no-esta.zip")


class TestZipSlip:
    """
    Un zip preparado no puede escribir fuera de las cuatro carpetas.

    El destino son carpetas REALES del usuario, así que una entrada con `..`
    o con ruta absoluta es una escritura arbitraria en su `$HOME`.
    """

    @pytest.mark.parametrize("nombre", [
        "../../evil.txt",
        "config/../../evil.txt",
        "/etc/evil.txt",
        "evil.txt",
        "otracosa/evil.txt",
    ])
    def test_escaping_entries_are_skipped(self, tmp_path, nombre):
        malo = tmp_path / "malo.zip"
        with zipfile.ZipFile(malo, "w") as zf:
            zf.writestr(MANIFEST_NAME, '{"app": "puntueitor"}')
            zf.writestr(nombre, "PWNED")

        resultado = restore_backup(malo)

        assert resultado.files == 0
        assert resultado.skipped == 1
        assert not (tmp_path / "evil.txt").exists()
        assert not (tmp_path.parent / "evil.txt").exists()

    def test_the_good_entries_still_go_through(self, tmp_path):
        """Descartar lo malo no puede llevarse por delante lo bueno."""
        mixto = tmp_path / "mixto.zip"
        with zipfile.ZipFile(mixto, "w") as zf:
            zf.writestr(MANIFEST_NAME, '{"app": "puntueitor"}')
            zf.writestr("../evil.txt", "PWNED")
            zf.writestr("config/config.json", "BUENO")

        resultado = restore_backup(mixto)

        assert (resultado.files, resultado.skipped) == (1, 1)
        assert paths.config_file().read_text() == "BUENO"


class TestDestino:
    def test_a_directory_gets_the_default_name(self, tmp_path, poblado):
        carpeta = tmp_path / "salida"
        carpeta.mkdir()

        resultado = create_backup(carpeta)

        assert resultado.path == carpeta / "puntueitor.zip"
        assert resultado.path.is_file()

    def test_creates_the_parent_directory(self, tmp_path, poblado):
        destino = tmp_path / "sin" / "crear" / "copia.zip"
        assert create_backup(destino).path.is_file()

    def test_a_failed_backup_keeps_the_previous_one(self, tmp_path, poblado, monkeypatch):
        """
        Lo importante de escribir a un temporal: si se corta a la mitad, la
        copia de antes —justo la que se iba a necesitar— sigue entera.
        """
        create_backup(poblado)
        bueno = poblado.read_bytes()

        import puntueitor.core.services.backup as modulo
        monkeypatch.setattr(
            modulo, "_copy_database",
            lambda *a: (_ for _ in ()).throw(sqlite3.Error("boom")),
        )

        with pytest.raises(BackupError):
            create_backup(poblado)

        assert poblado.read_bytes() == bueno
        assert not poblado.with_name(poblado.name + ".parcial").exists()


class TestDondeSeProponeGuardar:
    def test_reads_user_dirs(self, tmp_path):
        escritorio = tmp_path / "MiEscritorio"
        escritorio.mkdir()
        config = tmp_path / ".config"
        config.mkdir(parents=True, exist_ok=True)
        (config / "user-dirs.dirs").write_text(
            'XDG_DESKTOP_DIR="$HOME/MiEscritorio"\n'
        )

        assert desktop_dir() == escritorio
        assert default_backup_path() == escritorio / "puntueitor.zip"

    def test_falls_back_to_desktop_or_escritorio(self, tmp_path):
        (tmp_path / "Escritorio").mkdir()
        assert desktop_dir() == tmp_path / "Escritorio"

    def test_without_any_desktop_it_uses_home(self, tmp_path):
        """Nunca falla: el `$HOME` siempre existe y sirve."""
        assert desktop_dir() == tmp_path

    def test_a_desktop_that_does_not_exist_is_ignored(self, tmp_path):
        config = tmp_path / ".config"
        config.mkdir(parents=True, exist_ok=True)
        (config / "user-dirs.dirs").write_text('XDG_DESKTOP_DIR="$HOME/NoExiste"\n')

        assert desktop_dir() == tmp_path


def test_backup_of_an_empty_installation(tmp_path):
    """Sin nada que guardar sale un zip válido, no un error."""
    destino = tmp_path / "vacia.zip"

    resultado = create_backup(destino)

    assert resultado.files == 0
    with zipfile.ZipFile(destino) as zf:
        assert zf.namelist() == [MANIFEST_NAME]
