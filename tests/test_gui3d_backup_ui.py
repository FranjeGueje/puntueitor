"""
Las copias de seguridad del carrusel, ya fuera de `gui3d/app.py`.

Primer trozo que sale de esa clase de 148 métodos. Se prueba entero sin abrir
ventana porque las funciones reciben la aplicación como argumento: basta con
darles una de mentira. Lo que hace el trabajo de verdad —comprimir, restaurar—
sigue en `core/services/backup.py` y tiene sus propios tests.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from puntueitor.gui3d import backup_ui


class AppFalsa:
    """Lo poquito que estas funciones necesitan de la aplicación."""

    def __init__(self):
        self.avisos = []
        self.prompts = []
        self.confirmaciones = []
        self.notifier = SimpleNamespace(show=self.avisos.append)

    def _open_text_prompt(self, title, initial, on_accept):
        self.prompts.append((title, initial))
        self.acepta = on_accept

    def _ask_confirm(self, titulo, nota, si, accion, warning=0):
        self.confirmaciones.append(titulo)
        self.confirma = accion


class TestLaRutaQueSePide:
    def test_a_normal_path(self):
        assert backup_ui.parse_path("  /tmp/copia.zip  ") == Path("/tmp/copia.zip")

    def test_nothing_written_is_nothing(self):
        """
        Aceptar la cadena vacía sería crear un fichero llamado "" o restaurar
        desde el directorio actual.
        """
        assert backup_ui.parse_path("") is None
        assert backup_ui.parse_path("   ") is None
        assert backup_ui.parse_path(None) is None


class TestElMensaje:
    def test_it_says_the_name_and_the_size(self):
        resultado = SimpleNamespace(path=Path("/tmp/puntueitor.zip"), megabytes=27.74)

        mensaje = backup_ui.backup_message(resultado)

        assert "puntueitor.zip" in mensaje
        assert "27.7 MB" in mensaje

    def test_it_does_not_show_the_whole_path(self):
        """En un aviso del carrusel no cabe una ruta larga."""
        resultado = SimpleNamespace(
            path=Path("/home/alguien/muy/hondo/puntueitor.zip"), megabytes=1.0,
        )

        assert "/home/alguien" not in backup_ui.backup_message(resultado)


class TestCopiar:
    def test_it_proposes_a_path_already_written(self):
        """
        Es lo que hace que se pueda usar con el mando: basta con aceptar, sin
        teclear una ruta entera.
        """
        app = AppFalsa()

        backup_ui.ask_backup_path(app)

        titulo, inicial = app.prompts[0]
        assert inicial.endswith(".zip")

    def test_accepting_an_empty_path_does_nothing(self, monkeypatch):
        llamadas = []
        monkeypatch.setattr(
            backup_ui.backup, "create_backup", lambda r: llamadas.append(r),
        )
        app = AppFalsa()

        backup_ui.do_backup(app, "   ")

        assert llamadas == []
        assert app.avisos == []

    def test_it_reports_the_result(self, monkeypatch):
        monkeypatch.setattr(
            backup_ui.backup, "create_backup",
            lambda ruta: SimpleNamespace(path=ruta, megabytes=3.0),
        )
        app = AppFalsa()

        backup_ui.do_backup(app, "/tmp/x.zip")

        assert "x.zip" in app.avisos[0]

    def test_a_failure_is_shown_and_does_not_raise(self, monkeypatch):
        def falla(ruta):
            raise backup_ui.backup.BackupError("no hay sitio en el disco")

        monkeypatch.setattr(backup_ui.backup, "create_backup", falla)
        app = AppFalsa()

        backup_ui.do_backup(app, "/tmp/x.zip")

        assert app.avisos == ["no hay sitio en el disco"]


class TestRestaurar:
    def test_it_asks_for_confirmation_before_anything(self, monkeypatch):
        """
        Restaurar sobrescribe la biblioteca, los estados y las claves: no
        puede pasar por aceptar una ruta.
        """
        restauradas = []
        monkeypatch.setattr(
            backup_ui.backup, "restore_backup", lambda r: restauradas.append(r),
        )
        app = AppFalsa()

        backup_ui.confirm_restore(app, "/tmp/x.zip")

        assert app.confirmaciones, "tenía que preguntar"
        assert restauradas == [], "y no haber restaurado todavía"

    def test_an_empty_path_does_not_even_ask(self):
        app = AppFalsa()

        backup_ui.confirm_restore(app, "  ")

        assert app.confirmaciones == []

    def test_a_failure_is_shown_and_does_not_close(self, monkeypatch):
        """
        Si la restauración falla, la aplicación NO puede cerrarse: en disco
        siguen estando los datos buenos.
        """
        def falla(ruta):
            raise backup_ui.backup.BackupError("ese zip no es una copia")

        salidas = []
        monkeypatch.setattr(backup_ui.backup, "restore_backup", falla)
        monkeypatch.setattr(backup_ui.os, "_exit", lambda c: salidas.append(c))
        app = AppFalsa()

        backup_ui.do_restore(app, Path("/tmp/x.zip"))

        assert app.avisos == ["ese zip no es una copia"]
        assert salidas == [], "no debía cerrar"

    def test_a_good_restore_closes_hard(self, monkeypatch):
        """
        Con `os._exit`, no con el cierre ordenado: ese ESCRIBE —los filtros
        del carrusel y el estado de SQLite— encima de lo recién restaurado.
        """
        salidas = []
        monkeypatch.setattr(
            backup_ui.backup, "restore_backup",
            lambda r: SimpleNamespace(files=1289),
        )
        monkeypatch.setattr(backup_ui.os, "_exit", lambda c: salidas.append(c))

        backup_ui.do_restore(AppFalsa(), Path("/tmp/x.zip"))

        assert salidas == [0]


class TestYaNoEstanEnApp:
    """
    El objetivo del refactor: que estos métodos hayan SALIDO de la clase, no
    que estén en dos sitios.
    """

    def test_the_app_no_longer_has_them(self):
        from puntueitor.gui3d.app import App

        for metodo in ("_ask_backup_path", "_do_backup", "_ask_restore_path",
                       "_confirm_restore", "_do_restore"):
            assert not hasattr(App, metodo), metodo
