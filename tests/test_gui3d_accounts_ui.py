"""
Cuentas, Tiendas y los ajustes propios del carrusel, ya fuera de
`gui3d/app.py`.

Tercer trozo que sale de esa clase. Las tres pantallas comparten módulo
porque comparten mecánica: una copia en edición y "Guardar" que la aplica,
a diferencia de Avanzado o Créditos, que no editan nada.

Se prueba sin ventana con una aplicación de mentira; la parte que habla con
disco de verdad (`ConfigManager`, la sesión de una tienda) usa el sandbox de
`conftest.py`.
"""
import dataclasses
from types import SimpleNamespace

import pytest

from puntueitor.core.config import ConfigManager
from puntueitor.gui3d import accounts_ui, state
from puntueitor.gui3d.menu import MenuItem


class MenuFalso:
    def __init__(self, items=None):
        self.items = list(items or [])

    def set_items(self, items):
        self.items = items

    def refresh_values(self):
        pass


class AppFalsa:
    """Lo poquito que estas funciones necesitan de la aplicación."""

    def __init__(self):
        self.accounts_menu = MenuFalso()
        self.settings_menu = MenuFalso()
        self.gui3d_menu = MenuFalso()
        self.prefs = state.Preferences()
        self.filters = SimpleNamespace()
        self._labels_visible = True
        self.avisos = []
        self.notifier = SimpleNamespace(show=self.avisos.append)
        self.prompts = []
        self.menus_abiertos = []
        self.menus_cerrados = 0
        self.reordenado = False

    def _open_text_prompt(self, title, initial, on_accept):
        self.prompts.append((title, initial))
        self.acepta = on_accept

    def _push_menu(self, menu):
        self.menus_abiertos.append(menu)

    def _pop_menu(self):
        self.menus_cerrados += 1

    def _apply_order(self):
        self.reordenado = True

    def _on_selection_changed(self):
        pass

    def carousel(self):
        return SimpleNamespace(set_score_source=lambda *a: None)


class TestFiltrosRecordados:
    def test_it_saves_when_remembering(self, monkeypatch):
        guardados = []
        monkeypatch.setattr(state, "save_filters", lambda f: guardados.append(f))
        app = AppFalsa()
        app.prefs.remember_filters = True

        accounts_ui.persist_filters(app)

        assert guardados == [app.filters]

    def test_it_does_not_save_otherwise(self, monkeypatch):
        guardados = []
        monkeypatch.setattr(state, "save_filters", lambda f: guardados.append(f))
        app = AppFalsa()
        app.prefs.remember_filters = False

        accounts_ui.persist_filters(app)

        assert guardados == []


class TestAjustesDelCarrusel:
    def test_opening_edits_a_copy(self):
        app = AppFalsa()
        app.prefs.score_source = "steamdb"

        accounts_ui.open_gui3d_menu(app)

        assert app._gui3d_prefs is not app.prefs
        assert app.menus_abiertos == [app.gui3d_menu]

    def test_adjusting_the_score_source_cycles(self):
        app = AppFalsa()
        accounts_ui.open_gui3d_menu(app)
        app._gui3d_prefs.score_source = state.SCORE_SOURCES[0]

        accounts_ui.adjust_gui3d_setting(
            app, MenuItem("set3d:score_source", ""), direction=1,
        )

        assert app._gui3d_prefs.score_source == state.SCORE_SOURCES[1]

    def test_saving_writes_the_copy_and_closes(self, monkeypatch):
        guardados = []
        monkeypatch.setattr(state, "save_preferences", lambda p: guardados.append(p))
        app = AppFalsa()
        app.carousel = SimpleNamespace(set_score_source=lambda *a: None)
        accounts_ui.open_gui3d_menu(app)

        accounts_ui.save_gui3d_settings(app)

        assert guardados == [app._gui3d_prefs]
        assert app.prefs is app._gui3d_prefs
        assert app.menus_cerrados == 1

    def test_it_does_not_apply_until_saved(self):
        """Salir con B sin guardar no puede cambiar nada."""
        app = AppFalsa()
        original = app.prefs
        accounts_ui.open_gui3d_menu(app)
        app._gui3d_prefs.remember_filters = not original.remember_filters

        assert app.prefs is original


class TestCuentasYTiendas:
    def test_both_screens_edit_the_same_dict_at_once(self):
        """
        `app._settings` es UN diccionario con los campos de las dos pantallas
        a la vez —credenciales y tiendas—, no uno por pantalla. Es lo que
        impide que guardar desde una borre lo que la otra había puesto.
        """
        app = AppFalsa()
        accounts_ui.open_accounts_menu(app)

        assert "igdb_client_id" in app._settings
        assert "gog_is_active" in app._settings

    def test_reopening_remembers_which_screen_to_refresh(self):
        """
        `_settings_builder` es lo que usa `refresh_settings_menu` para saber
        a cuál de los dos menús repintar sin preguntarlo.
        """
        app = AppFalsa()

        accounts_ui.open_settings_menu(app)
        assert app._settings_builder is not None

        accounts_ui.open_accounts_menu(app)
        assert app._settings_builder is not None

    def test_opening_accounts_shows_the_sessions(self, monkeypatch):
        monkeypatch.setattr(
            accounts_ui, "read_sessions", lambda: {"gog": True},
        )
        app = AppFalsa()

        accounts_ui.open_accounts_menu(app)

        assert app._sessions == {"gog": True}
        assert app.menus_abiertos == [app.accounts_menu]

    def test_a_text_field_opens_a_prompt_with_the_current_value(self):
        app = AppFalsa()
        accounts_ui.open_settings_menu(app)
        app._settings["igdb_client_id"] = "ya-puesto"

        accounts_ui.activate_setting(app, "set:igdb_client_id")

        assert app.prompts[0][1] == "ya-puesto"

    def test_a_login_row_starts_the_login(self, monkeypatch):
        iniciados = []
        monkeypatch.setattr(
            accounts_ui, "start_login", lambda app, store: iniciados.append(store),
        )
        app = AppFalsa()
        accounts_ui.open_accounts_menu(app)

        accounts_ui.activate_setting(app, "login:gog")

        assert iniciados == ["gog"]

    def test_a_checkbox_flips_the_flag(self):
        app = AppFalsa()
        accounts_ui.open_settings_menu(app)
        item = MenuItem("set:gog_is_active", "GOG", checked=True,
                         payload={"field": "gog_is_active"})

        accounts_ui.toggle_setting_store(app, item)

        assert app._settings["gog_is_active"] is True

    def test_a_numeric_field_falls_back_to_zero(self):
        """Igual que la TUI: lo que no se entienda se queda en 0."""
        app = AppFalsa()
        accounts_ui.open_settings_menu(app)

        accounts_ui.set_setting(app, "steam_user_id", "no-es-un-número")

        assert app._settings["steam_user_id"] == 0

    def test_saving_writes_to_the_real_config(self):
        app = AppFalsa()
        accounts_ui.open_settings_menu(app)
        app._settings["gog_is_active"] = True

        accounts_ui.save_settings(app)

        assert ConfigManager().get.gog_is_active is True
        assert app.reordenado
        assert app.menus_cerrados == 1

    def test_saving_reorders_because_active_stores_change_what_shows(self):
        """Las tiendas marcadas deciden qué se ve, no solo qué se carga."""
        app = AppFalsa()
        accounts_ui.open_accounts_menu(app)

        accounts_ui.save_settings(app)

        assert app.reordenado


class TestLogin:
    def test_a_successful_open_asks_to_paste(self, monkeypatch):
        from puntueitor.core.services import accounts as accounts_service

        monkeypatch.setattr(
            accounts_service, "open_login",
            lambda store: SimpleNamespace(ok=True, mensaje="Navegador abierto"),
        )
        app = AppFalsa()

        accounts_ui.start_login(app, "gog")

        assert app.avisos == ["Navegador abierto"]
        assert app.prompts, "tenía que pedir el pegado"

    def test_a_failed_open_does_not_ask_to_paste(self, monkeypatch):
        from puntueitor.core.services import accounts as accounts_service

        monkeypatch.setattr(
            accounts_service, "open_login",
            lambda store: SimpleNamespace(ok=False, mensaje="Sin navegador"),
        )
        app = AppFalsa()

        accounts_ui.start_login(app, "gog")

        assert app.prompts == []

    def test_finishing_refreshes_the_sessions(self, monkeypatch):
        from puntueitor.core.services import accounts as accounts_service

        monkeypatch.setattr(
            accounts_service, "finish_login",
            lambda store, texto: SimpleNamespace(ok=True, mensaje="Sesión iniciada"),
        )
        monkeypatch.setattr(accounts_ui, "read_sessions", lambda: {"gog": True})
        app = AppFalsa()
        accounts_ui.open_accounts_menu(app)

        accounts_ui.finish_login(app, "gog", "https://x/?code=1")

        assert app._sessions == {"gog": True}
        assert app.avisos == ["Sesión iniciada"]


class TestYaNoEstanEnApp:
    def test_the_app_no_longer_has_them(self):
        from puntueitor.gui3d.app import App

        for metodo in (
            "_persist_filters", "_open_gui3d_menu", "_adjust_gui3d_setting",
            "_save_gui3d_settings", "_refresh_gui3d_menu",
            "_open_accounts_menu", "_open_settings_menu", "_open_config_form",
            "_refresh_settings_menu", "_read_sessions", "_activate_setting",
            "_start_login", "_finish_login", "_set_setting",
            "_toggle_setting_store", "_save_settings",
        ):
            assert not hasattr(App, metodo), metodo
