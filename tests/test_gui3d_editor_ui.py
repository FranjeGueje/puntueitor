"""
El Editor Rápido, ya fuera de `gui3d/app.py`.

Cuarto trozo, y el más pequeño de lo estimado: el bloque de comentario
"Editor Rápido" del fichero original incluía métodos del modo Desconocidos
que no son de aquí, y dos de los suyos —`_blocked_in_editor`,
`_persist_flags`— se quedan en `App` porque los usa también el menú de juego
o se llaman desde seis sitios distintos del fichero.

Se prueba sin ventana con una aplicación de mentira. La histéresis del stick
—que no marque dos veces por mantener la palanca echada— ya la cubre
`tests/test_gui3d_gamepad.py` a nivel de `GamepadInput`; aquí se prueba que
`update_editor` respeta el flanco que esa clase ya calcula.
"""
from types import SimpleNamespace

import pytest

from tests.conftest import AudioDoble

from puntueitor.gui3d import editor_ui, menus


class CarouselFalso:
    def __init__(self, selected=None):
        self.selected = selected
        self.reetiquetados = []

    def rebuild_labels(self, key, game, visible):
        self.reetiquetados.append(key)


class GamepadFalso:
    def __init__(self, direccion=(0, 0)):
        self._direccion = direccion

    def right_stick(self):
        return self._direccion


class TextoFalso:
    def __init__(self):
        self.visible = False

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False


class AppFalsa:
    def __init__(self, entry=None, editor_mode=False, gamepad=None):
        self._typing = False
        self.active_menu = None
        self._unknown_mode = False
        self._editor_mode = editor_mode
        self._editor_stick = (0, 0)
        self._hidden_filter_dirty = False
        self.help_text = TextoFalso()
        self.editor_help_text = TextoFalso()
        self.gamepad = gamepad
        self.carousel = CarouselFalso(entry)
        self._labels_visible = True
        self.avisos = []
        self.notifier = SimpleNamespace(show=self.avisos.append)
        self.flags_guardados = []
        self.filtro_aplicado = False
        self.audio = AudioDoble()

    def _apply_hidden_filter(self):
        self.filtro_aplicado = True

    def _persist_flags(self, game):
        self.flags_guardados.append(game)


class Entrada:
    def __init__(self, key, game):
        self.key = key
        self.game = game


class TestEntrarYSalir:
    def test_it_toggles_on(self):
        app = AppFalsa()

        editor_ui.toggle_editor_mode(app)

        assert app._editor_mode
        assert app.editor_help_text.visible
        assert not app.help_text.visible
        assert app.avisos == [menus.EDITOR_ON]

    def test_it_toggles_off(self):
        app = AppFalsa(editor_mode=True)

        editor_ui.toggle_editor_mode(app)

        assert not app._editor_mode
        assert app.help_text.visible
        assert app.avisos == [menus.EDITOR_OFF]

    def test_leaving_applies_the_pending_hidden_filter(self):
        """
        Lo que se haya ocultado durante la sesión se aplica AL SALIR, no al
        momento: si no, la caja que acabas de marcar desaparecería de debajo
        mientras sigues editando.
        """
        app = AppFalsa(editor_mode=True)
        app._hidden_filter_dirty = True

        editor_ui.toggle_editor_mode(app)

        assert app.filtro_aplicado
        assert not app._hidden_filter_dirty

    def test_it_forgets_the_last_stick_position(self):
        """Si se sale y se entra con el stick echado, cuenta como flanco nuevo."""
        app = AppFalsa()
        app._editor_stick = (1, 0)

        editor_ui.toggle_editor_mode(app)

        assert app._editor_stick == (0, 0)

    def test_it_does_not_open_while_typing(self):
        app = AppFalsa()
        app._typing = True

        editor_ui.toggle_editor_mode(app)

        assert not app._editor_mode

    def test_it_does_not_open_with_a_menu_on_top(self):
        app = AppFalsa()
        app.active_menu = object()

        editor_ui.toggle_editor_mode(app)

        assert not app._editor_mode

    def test_it_refuses_in_unknown_mode(self):
        app = AppFalsa()
        app._unknown_mode = True

        editor_ui.toggle_editor_mode(app)

        assert not app._editor_mode
        assert "biblioteca" in app.avisos[0]


class TestElFlanco:
    """
    Sin esto, mantener el stick echado marcaría y desmarcaría el estado
    sesenta veces por segundo.
    """

    def test_a_new_direction_fires_the_gesture(self, make_game):
        juego = make_game(igdb_id=1, title="X")
        app = AppFalsa(
            entry=Entrada(1, juego), editor_mode=True,
            gamepad=GamepadFalso((0, -1)),
        )

        editor_ui.update_editor(app)

        assert juego.backlog is True

    def test_holding_it_does_not_fire_again(self, make_game):
        juego = make_game(igdb_id=1, title="X")
        app = AppFalsa(
            entry=Entrada(1, juego), editor_mode=True,
            gamepad=GamepadFalso((0, -1)),
        )
        app._editor_stick = (0, -1)  # ya estaba en esa posición

        editor_ui.update_editor(app)

        assert juego.backlog is False, "no debía volver a conmutar"

    def test_releasing_does_not_fire_a_gesture(self, make_game):
        juego = make_game(igdb_id=1, title="X")
        app = AppFalsa(
            entry=Entrada(1, juego), editor_mode=True,
            gamepad=GamepadFalso((0, 0)),
        )
        app._editor_stick = (0, -1)

        editor_ui.update_editor(app)

        assert app._editor_stick == (0, 0)
        assert juego.backlog is False

    def test_it_does_nothing_outside_editor_mode(self, make_game):
        juego = make_game(igdb_id=1, title="X")
        app = AppFalsa(entry=Entrada(1, juego), gamepad=GamepadFalso((0, -1)))

        editor_ui.update_editor(app)

        assert juego.backlog is False

    def test_it_does_nothing_without_a_gamepad(self, make_game):
        juego = make_game(igdb_id=1, title="X")
        app = AppFalsa(entry=Entrada(1, juego), editor_mode=True, gamepad=None)

        editor_ui.update_editor(app)  # no debe reventar


class TestElGesto:
    def test_it_toggles_the_field_and_saves(self, make_game):
        juego = make_game(igdb_id=1, title="X", finished=False)
        app = AppFalsa(entry=Entrada(1, juego), editor_mode=True)

        editor_ui.editor_gesture(app, (0, 1))  # abajo = finished

        assert juego.finished is True
        assert app.flags_guardados == [juego]
        assert app.carousel.reetiquetados == [1]

    def test_it_announces_what_changed(self, make_game):
        juego = make_game(igdb_id=1, title="X")
        app = AppFalsa(entry=Entrada(1, juego), editor_mode=True)

        editor_ui.editor_gesture(app, (1, 0))  # derecha = favorite

        assert app.avisos

    def test_hiding_does_not_re_filter_immediately(self, make_game):
        """
        La caja que acabas de marcar no puede desaparecer de debajo mientras
        sigues editando: se apunta y se aplica al SALIR (ver `toggle_editor_mode`).
        """
        juego = make_game(igdb_id=1, title="X")
        app = AppFalsa(entry=Entrada(1, juego), editor_mode=True)

        editor_ui.editor_gesture(app, (-1, 0))  # izquierda = hidden

        assert app._hidden_filter_dirty
        assert not app.filtro_aplicado

    def test_it_does_nothing_outside_editor_mode(self, make_game):
        juego = make_game(igdb_id=1, title="X", finished=False)
        app = AppFalsa(entry=Entrada(1, juego))

        editor_ui.editor_gesture(app, (0, 1))

        assert juego.finished is False

    def test_it_does_nothing_while_typing(self, make_game):
        juego = make_game(igdb_id=1, title="X", finished=False)
        app = AppFalsa(entry=Entrada(1, juego), editor_mode=True)
        app._typing = True

        editor_ui.editor_gesture(app, (0, 1))

        assert juego.finished is False

    def test_no_selection_does_not_raise(self):
        app = AppFalsa(entry=None, editor_mode=True)

        editor_ui.editor_gesture(app, (0, 1))  # no debe reventar

        assert app.flags_guardados == []


class TestYaNoEstanEnApp:
    def test_the_app_no_longer_has_them(self):
        from puntueitor.gui3d.app import App

        for metodo in ("_toggle_editor_mode", "_update_editor", "_editor_gesture"):
            assert not hasattr(App, metodo), metodo

    def test_the_shared_guards_stayed_behind(self):
        """
        `_blocked_in_editor` la llaman seis sitios de fuera del editor, y
        `_persist_flags` la comparte con el menú de juego.
        """
        from puntueitor.gui3d.app import App

        assert hasattr(App, "_blocked_in_editor")
        assert hasattr(App, "_persist_flags")
