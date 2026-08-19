"""
Elegir un sistema de puntuación y configurar sus pesos, desde el carrusel.

Tercer trozo que sale de `gui3d/app.py`: era el bloque marcado "Scoring", que
en realidad incluía también el diálogo de sí/no genérico y las casillas del
menú de juego — dos cosas que se quedan en `App` a propósito, porque no son
de scoring y una de ellas ya la usa `backup_ui.py`.

Se prueba sin ventana, con una aplicación de mentira: las funciones reciben
`app` explícito, así que basta con darles algo que tenga los atributos que
usan.
"""
from types import SimpleNamespace

import pytest

from puntueitor.gui3d import scoring_ui
from puntueitor.gui3d.menu import MenuItem


class MenuFalso:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.focused_item = self.items[0] if self.items else None
        self.title = ""

    def set_title(self, titulo):
        self.title = titulo

    def set_items(self, items):
        self.items = items

    def refresh_values(self):
        pass


class TextoFalso:
    def __init__(self):
        self.texto = ""

    def setText(self, texto):
        self.texto = texto


class FrameFalso:
    def __init__(self):
        self.visible = False

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False


class AppFalsa:
    """Lo poquito que estas funciones necesitan de la aplicación."""

    def __init__(self, entries=None):
        self.entries = list(entries or [])
        self.library_repository = object()
        self.scoring_menu = MenuFalso([MenuItem("mixed", "Mixed Score")])
        self.scoring_config_menu = MenuFalso()
        self.scoring_title_text = TextoFalso()
        self.scoring_desc_text = TextoFalso()
        self.scoring_frame = FrameFalso()
        self.avisos = []
        self.notifier = SimpleNamespace(show=self.avisos.append)
        self.menus_abiertos = []
        self.menus_cerrados = 0
        self._sort_criterion = None

    def _push_menu(self, menu):
        self.menus_abiertos.append(menu)

    def _pop_menu(self):
        self.menus_cerrados += 1

    def _close_all_menus(self):
        self.menus_cerrados += 1

    def _apply_order(self, reset_selection=False):
        pass

    def _on_selection_changed(self):
        pass


class TestLaDescripcion:
    def test_it_shows_the_focused_system(self):
        app = AppFalsa()

        scoring_ui.refresh_scoring_description(app)

        assert "Mixed Score" in app.scoring_title_text.texto
        assert app.scoring_desc_text.texto

    def test_nothing_focused_does_not_raise(self):
        app = AppFalsa()
        app.scoring_menu.focused_item = None

        scoring_ui.refresh_scoring_description(app)  # no debe reventar

    def test_showing_it_refreshes_first(self):
        app = AppFalsa()

        scoring_ui.show_scoring_description(app, True)

        assert app.scoring_frame.visible
        assert app.scoring_title_text.texto

    def test_hiding_it_does_not_touch_the_text(self):
        app = AppFalsa()

        scoring_ui.show_scoring_description(app, False)

        assert not app.scoring_frame.visible
        assert app.scoring_title_text.texto == ""


class TestPuntuar:
    def test_an_unknown_system_does_nothing(self):
        app = AppFalsa()

        scoring_ui.apply_scorer(app, "no-existe")

        assert app.avisos == []
        assert app._sort_criterion is None

    def test_no_games_no_score_says_so(self):
        app = AppFalsa(entries=[])

        scoring_ui.apply_scorer(app, "mixed")

        assert any("no ha podido puntuar" in a for a in app.avisos)

    def test_it_closes_the_menus_and_orders(self, make_game):
        juego = make_game(
            igdb_id=1, title="X", critic_score=80, user_score=90,
            duration_hours=10,
        )
        app = AppFalsa(entries=[SimpleNamespace(game=juego)])

        scoring_ui.apply_scorer(app, "mixed")

        assert app.menus_cerrados == 1
        assert app._sort_criterion is not None
        assert any("Puntuado" in a for a in app.avisos)


class TestElFormularioDeConfiguracion:
    def test_opening_it_loads_the_saved_weights(self, monkeypatch):
        from puntueitor.core.scoring import catalog

        monkeypatch.setattr(
            scoring_ui.scoring_config, "weights_of",
            lambda key: {"critics": 30.0, "users": 50.0, "duration": 20.0},
        )
        app = AppFalsa()

        scoring_ui.open_scoring_config(app, catalog.get("mixed"))

        assert app._config_weights["users"] == 50.0
        assert app.menus_abiertos == [app.scoring_config_menu]

    def test_the_sum_is_always_shown(self, monkeypatch):
        from puntueitor.core.scoring import catalog

        monkeypatch.setattr(
            scoring_ui.scoring_config, "weights_of",
            lambda key: {"critics": 30.0, "users": 50.0, "duration": 20.0},
        )
        app = AppFalsa()
        app._config_scorer = catalog.get("mixed")
        app._config_weights = {"critics": 30.0, "users": 50.0, "duration": 20.0}

        items = scoring_ui.build_config_items(app)

        assert any(i.key == "cfg:sum" for i in items)

    def test_adjusting_a_weight_is_clamped(self, monkeypatch):
        from puntueitor.core.scoring import catalog

        monkeypatch.setattr(scoring_ui, "refresh_config_menu", lambda app: None)
        app = AppFalsa()
        app._config_scorer = catalog.get("mixed")
        app._config_weights = {"critics": 99.0, "users": 0.0, "duration": 0.0}
        item = MenuItem("cfg:weight:critics", "", payload={"weight": "critics"})

        scoring_ui.adjust_config_value(app, item, direction=5)

        assert app._config_weights["critics"] == 100.0

    def test_saving_invalid_weights_warns_and_does_not_close(self, monkeypatch):
        from puntueitor.core.scoring import catalog

        monkeypatch.setattr(scoring_ui.scoring_config, "save_weights", lambda k, w: False)
        app = AppFalsa()
        app._config_scorer = catalog.get("mixed")
        app._config_weights = {"critics": 10.0, "users": 10.0, "duration": 10.0}

        scoring_ui.save_scoring_config(app)

        assert "sumar 100" in app.avisos[0]
        assert app.menus_cerrados == 0

    def test_saving_valid_weights_closes_the_menu(self, monkeypatch):
        from puntueitor.core.scoring import catalog

        monkeypatch.setattr(scoring_ui.scoring_config, "save_weights", lambda k, w: True)
        app = AppFalsa()
        app._config_scorer = catalog.get("mixed")
        app._config_weights = {"critics": 40.0, "users": 40.0, "duration": 20.0}

        scoring_ui.save_scoring_config(app)

        assert app.menus_cerrados == 1

    def test_resetting_restores_the_defaults(self, monkeypatch):
        from puntueitor.core.scoring import catalog

        monkeypatch.setattr(
            scoring_ui.scoring_config, "default_weights",
            lambda key: {"critics": 30.0, "users": 50.0, "duration": 20.0},
        )
        monkeypatch.setattr(scoring_ui, "refresh_config_menu", lambda app: None)
        app = AppFalsa()
        app._config_scorer = catalog.get("mixed")
        app._config_weights = {"critics": 0.0, "users": 0.0, "duration": 0.0}

        scoring_ui.reset_scoring_config(app)

        assert app._config_weights["users"] == 50.0
        assert any("restaurados" in a for a in app.avisos)


class TestActivarUnaFilaDelFormulario:
    def test_save_calls_save(self, monkeypatch):
        llamadas = []
        monkeypatch.setattr(scoring_ui, "save_scoring_config", lambda app: llamadas.append("save"))

        scoring_ui.activate_config(AppFalsa(), "cfg:save")

        assert llamadas == ["save"]

    def test_reset_calls_reset(self, monkeypatch):
        llamadas = []
        monkeypatch.setattr(scoring_ui, "reset_scoring_config", lambda app: llamadas.append("reset"))

        scoring_ui.activate_config(AppFalsa(), "cfg:reset")

        assert llamadas == ["reset"]

    def test_a_weight_or_hours_row_does_nothing_on_accept(self):
        """Esas se ajustan con izquierda/derecha, no con A."""
        app = AppFalsa()

        scoring_ui.activate_config(app, "cfg:weight:critics")  # no debe reventar


class TestGeneros:
    def test_checking_adds_it(self):
        app = AppFalsa()
        app._config_genres = set()
        item = MenuItem("cfg:genre:RPG", "RPG", checked=True, payload={"genre": "RPG"})

        scoring_ui.toggle_config_genre(app, item)

        assert "RPG" in app._config_genres

    def test_unchecking_removes_it(self):
        app = AppFalsa()
        app._config_genres = {"RPG"}
        item = MenuItem("cfg:genre:RPG", "RPG", checked=False, payload={"genre": "RPG"})

        scoring_ui.toggle_config_genre(app, item)

        assert "RPG" not in app._config_genres


class TestYaNoEstanEnApp:
    def test_the_app_no_longer_has_them(self):
        from puntueitor.gui3d.app import App

        for metodo in (
            "_refresh_scoring_description", "_show_scoring_description",
            "_apply_scorer", "_configure_focused_scoring",
            "_open_scoring_config", "_build_config_items",
            "_refresh_config_menu", "_activate_config",
            "_adjust_config_value", "_toggle_config_genre",
            "_save_scoring_config", "_reset_scoring_config",
        ):
            assert not hasattr(App, metodo), metodo

    def test_the_flag_toggle_stayed_behind(self):
        """No es de scoring, es del menú de juego."""
        from puntueitor.gui3d.app import App

        assert hasattr(App, "_on_game_flag_toggled")

    def test_the_generic_confirm_stayed_behind(self):
        """Ya lo usa backup_ui; moverlo aquí crearía el ciclo que se evita."""
        from puntueitor.gui3d.app import App

        assert hasattr(App, "_ask_confirm")
        assert hasattr(App, "_run_confirmed_action")
