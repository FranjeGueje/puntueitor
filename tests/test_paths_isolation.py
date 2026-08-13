"""
Que la suite no pueda tocar los ficheros reales del usuario.

Estos tests existen por un incidente concreto: `core/paths.py` migraba
ficheros al importarse, y como medio proyecto lo importa, arrancar `pytest`
movía ficheros del `$HOME` real antes de que ningún fixture pudiera actuar.
Se llegaron a mover `config.json` y `filter_state.json` de verdad.
"""
import os
from pathlib import Path

from puntueitor.core import paths


REAL_HOME = Path(os.path.expanduser("~"))


class TestAislamiento:
    def test_ninguna_ruta_apunta_al_home_real(self):
        rutas = (
            paths.config_dir(), paths.data_dir(), paths.cache_dir(),
            paths.state_dir(), paths.config_file(), paths.scoring_file(),
            paths.main_db(), paths.library_db(), paths.covers_dir(),
            paths.igdb_token_file(), paths.log_file(),
            paths.tui_state_file(), paths.gui3d_state_file(),
        )
        for ruta in rutas:
            assert not str(ruta).startswith(str(REAL_HOME)), ruta

    def test_los_origenes_de_migracion_tampoco(self):
        """
        El caso que se escapó: `_legacy_moves()` construye los ORÍGENES con
        `Path.home()` porque son rutas anteriores al sistema XDG. Parchear
        solo las variables XDG dejaba los orígenes en el home real, y la
        migración se llevaba los ficheros del usuario a un temporal.
        """
        for origen, destino in paths._legacy_moves():
            assert not str(origen).startswith(str(REAL_HOME)), origen
            assert not str(destino).startswith(str(REAL_HOME)), destino


class TestImportarNoTocaElDisco:
    def test_importar_paths_no_crea_directorios(self, tmp_path, monkeypatch):
        """
        Importar el módulo no debe crear nada. Se comprueba recargándolo con
        el home en un directorio vacío: si al importarse hiciera `mkdir` o
        migrara algo, aparecerían ficheros.
        """
        import importlib

        vacio = tmp_path / "hogar-limpio"
        vacio.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: vacio))
        for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME",
                         "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            monkeypatch.delenv(variable, raising=False)

        importlib.reload(paths)

        assert list(vacio.iterdir()) == [], list(vacio.iterdir())

    def test_la_migracion_hay_que_pedirla(self, tmp_path, monkeypatch):
        """
        Y cuando se pide explícitamente, sí migra: la funcionalidad no se ha
        perdido al sacarla del import, solo ha dejado de ser automática.
        """
        hogar = tmp_path / "hogar"
        antiguo = hogar / ".config" / "puntueitor"
        antiguo.mkdir(parents=True)
        (antiguo / "filter_state.json").write_text('{"show_hidden": true}')

        monkeypatch.setattr(Path, "home", staticmethod(lambda: hogar))
        for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME",
                         "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            monkeypatch.delenv(variable, raising=False)

        assert not paths.tui_state_file().exists()

        paths.migrate_legacy_paths()

        assert paths.tui_state_file().read_text() == '{"show_hidden": true}'
        assert not (antiguo / "filter_state.json").exists()
