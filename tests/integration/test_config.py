import json
import pytest
from pathlib import Path

from puntueitor.core import paths
from puntueitor.core.config import (
    Config,
    ConfigManager,
    ScoringConfig,
    load_scoring,
    save_scoring,
)


class TestConfigManager:
    def test_singleton(self):
        cm1 = ConfigManager()
        cm2 = ConfigManager()
        assert cm1 is cm2

    def test_default_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        cm = ConfigManager()
        cfg = cm.get
        assert cfg.steam_api_key == ""
        assert cfg.igdb_client_id == ""

    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        cm = ConfigManager()
        cm.config = Config(
            steam_api_key="test_key",
            steam_user_id=12345,
            igdb_client_id="test_client",
            igdb_client_secret="test_secret",
        )
        cm.save()

        ConfigManager._instance = None
        cm2 = ConfigManager()
        cfg = cm2.get
        assert cfg.steam_api_key == "test_key"
        assert cfg.steam_user_id == 12345
        assert cfg.igdb_client_id == "test_client"
        assert cfg.igdb_client_secret == "test_secret"

    def test_load_corrupted_json(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".config" / "puntueitor"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text("{invalid json}")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        cm = ConfigManager()
        cfg = cm.get
        assert cfg.steam_api_key == ""

    def test_load_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        cm = ConfigManager()
        cfg = cm.get
        assert cfg.steam_api_key == ""

    def test_extra_fields_ignored(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".config" / "puntueitor"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(json.dumps({
            "steam_api_key": "key",
            "nonexistent_field": "should_be_ignored",
        }))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        cm = ConfigManager()
        assert cm.get.steam_api_key == "key"
        assert not hasattr(cm.get, "nonexistent_field")

    def test_save_keeps_unknown_keys(self, tmp_path, monkeypatch):
        """Guardar no debe tirar claves que haya en disco y `Config` no conozca."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config_dir = tmp_path / ".config" / "puntueitor"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(json.dumps({
            "steam_api_key": "key",
            "algo_de_otro": 42,
        }))

        cm = ConfigManager()
        cm.save()

        data = json.loads((config_dir / "config.json").read_text())
        assert data["algo_de_otro"] == 42
        assert data["steam_api_key"] == "key"


class TestScoringConfig:
    """Los ajustes de scoring viven en su propio fichero, no en config.json."""

    def test_defaults_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        scoring = load_scoring()
        assert scoring.scoring_available_hours == 20.0
        assert scoring.scoring_preferred_genres == []

    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        scoring = load_scoring()
        scoring.scoring_mixed_critics = 0.4
        scoring.scoring_mixed_users = 0.45
        scoring.scoring_mixed_duration = 0.15
        scoring.scoring_preferred_genres = ["Strategy"]
        save_scoring(scoring)

        recargado = load_scoring()
        assert recargado.scoring_mixed_critics == 0.4
        assert recargado.scoring_mixed_users == 0.45
        assert recargado.scoring_mixed_duration == 0.15
        assert recargado.scoring_preferred_genres == ["Strategy"]

    def test_written_to_its_own_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        save_scoring(ScoringConfig(scoring_available_hours=33.0))

        data = json.loads(paths.scoring_file().read_text())
        assert data["scoring_available_hours"] == 33.0
        assert "steam_api_key" not in data

    def test_migrates_from_config_json(self, tmp_path, monkeypatch):
        """Un config.json de los de antes se vuelca a scoring.json y se limpia."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config_dir = tmp_path / ".config" / "puntueitor"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(json.dumps({
            "steam_api_key": "no_me_toques",
            "igdb_client_secret": "secreto",
            "scoring_mixed_critics": 0.4,
            "scoring_mixed_users": 0.45,
            "scoring_mixed_duration": 0.15,
            "scoring_available_hours": 20.0,
            "scoring_preferred_genres": ["Strategy", "Tactical"],
        }))

        scoring = load_scoring()
        assert scoring.scoring_mixed_users == 0.45
        assert scoring.scoring_preferred_genres == ["Strategy", "Tactical"]

        # Los valores acaban en el fichero nuevo...
        nuevo = json.loads(paths.scoring_file().read_text())
        assert nuevo["scoring_mixed_users"] == 0.45

        # ...y salen del viejo, que conserva intactas las credenciales.
        viejo = json.loads((config_dir / "config.json").read_text())
        assert viejo["steam_api_key"] == "no_me_toques"
        assert viejo["igdb_client_secret"] == "secreto"
        assert not [k for k in viejo if k.startswith("scoring_")]

    def test_migration_does_not_rerun(self, tmp_path, monkeypatch):
        """Con scoring.json ya creado, config.json deja de mandar."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config_dir = tmp_path / ".config" / "puntueitor"
        config_dir.mkdir(parents=True, exist_ok=True)

        save_scoring(ScoringConfig(scoring_available_hours=99.0))
        (config_dir / "config.json").write_text(json.dumps({
            "scoring_available_hours": 5.0,
        }))

        assert load_scoring().scoring_available_hours == 99.0

    def test_corrupted_scoring_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        paths.scoring_file().parent.mkdir(parents=True, exist_ok=True)
        paths.scoring_file().write_text("{roto")

        assert load_scoring().scoring_available_hours == 20.0

    def test_write_is_atomic(self, tmp_path, monkeypatch):
        """Si el volcado falla, el fichero anterior sigue entero."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        save_scoring(ScoringConfig(scoring_available_hours=42.0))

        import puntueitor.core.config as config_module

        def revienta(*args, **kwargs):
            raise RuntimeError("disco lleno")

        # `monkeypatch.context()` y NO `monkeypatch.undo()`: lo segundo
        # deshace también el aislamiento de `conftest`, y el resto del test
        # acabaría escribiendo en los ficheros reales del usuario.
        with monkeypatch.context() as m:
            m.setattr(config_module.json, "dump", revienta)
            with pytest.raises(RuntimeError):
                save_scoring(ScoringConfig(scoring_available_hours=1.0))

        assert load_scoring().scoring_available_hours == 42.0
        # Y no se queda basura al lado.
        assert not list(paths.scoring_file().parent.glob("*.tmp"))
