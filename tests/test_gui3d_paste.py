"""
Pegar el portapapeles en el cuadro de texto del carrusel.

Aquí se prueba el CAMINO, no la aritmética (esa está en
`test_gui3d_text_prompt.py`): que pulsar X con el cuadro abierto acabe
pegando, y que lo que se le dice al usuario corresponda con lo que ha
pasado.

Es el test que faltó la vez anterior con el menú de Cuentas: las filas se
pintaban bien y aun así elegirlas no hacía nada, porque nadie cubría el
tramo entre el gesto y la acción. `_on_filter_key` y `_paste_into_prompt`
son métodos que solo miran atributos, así que se les puede llamar con un
objeto de mentira por `self`, sin abrir ninguna ventana.
"""
import pytest

from puntueitor.core.services import clipboard


class PromptDoble:
    def __init__(self, is_open=True, pegados=9):
        self.is_open = is_open
        self._pegados = pegados
        self.recibido = None

    def paste(self, texto):
        self.recibido = texto
        return self._pegados


class AppFalsa:
    """Lo poquito que `_on_filter_key` y `_paste_into_prompt` miran."""

    def __init__(self, prompt=None, typing=True):
        self.text_prompt = prompt if prompt is not None else PromptDoble()
        self._typing = typing
        self.active_menu = None
        self.scoring_menu = object()
        self.avisos = []
        self.notifier = type(
            "N", (), {"show": lambda _s, m: self.avisos.append(m)},
        )()
        self.filtros_abiertos = 0

    def _paste_into_prompt(self):
        # El de verdad: así el test de X cubre el camino ENTERO, del botón
        # al portapapeles, y no solo que se llama a algo.
        from puntueitor.gui3d.app import App

        App._paste_into_prompt(self)

    def _open_filter_menu(self):
        self.filtros_abiertos += 1

    def _blocked_in_unknown_mode(self, _que):
        return False

    def _blocked_in_editor(self, _que):
        return False


def _app():
    from puntueitor.gui3d.app import App

    return App


@pytest.fixture
def portapapeles(monkeypatch):
    def montar(texto="", motivo=""):
        monkeypatch.setattr(
            clipboard, "read_clipboard", lambda: (texto, motivo),
        )
    return montar


class TestElBotonX:
    """
    X hace tres cosas según dónde estés. Con el cuadro abierto, pegar.

    El mando no pasa por el teclado, así que X ya llegaba hasta aquí mientras
    se escribía — solo que se iba de vacío por `self._typing`.
    """

    def test_with_the_prompt_open_it_pastes(self, portapapeles):
        portapapeles(texto="https://x/?code=ABC")
        app = AppFalsa()

        _app()._on_filter_key(app)

        assert app.text_prompt.recibido == "https://x/?code=ABC"

    def test_it_does_not_open_the_filter_menu_while_typing(self, portapapeles):
        portapapeles(texto="algo")
        app = AppFalsa()

        _app()._on_filter_key(app)

        assert app.filtros_abiertos == 0

    def test_with_the_prompt_closed_it_still_opens_the_filters(self):
        app = AppFalsa(prompt=PromptDoble(is_open=False), typing=False)

        _app()._on_filter_key(app)

        assert app.filtros_abiertos == 1


class TestPegar:
    def test_it_says_how_much_went_in(self, portapapeles):
        portapapeles(texto="123456789")
        app = AppFalsa(prompt=PromptDoble(pegados=9))

        _app()._paste_into_prompt(app)

        assert any("9" in aviso for aviso in app.avisos)

    def test_the_reason_reaches_the_user(self, portapapeles):
        """
        Sin portapapeles accesible —el modo juego del Deck— hay que decirlo,
        no quedarse callado mirando un cuadro que no cambia.
        """
        portapapeles(motivo="el portapapeles está vacío")
        app = AppFalsa()

        _app()._paste_into_prompt(app)

        assert app.avisos == ["el portapapeles está vacío"]
        assert app.text_prompt.recibido is None, "no debía intentar pegar"

    def test_pasting_nothing_useful_is_also_reported(self, portapapeles):
        """Si el portapapeles solo traía saltos, no entra nada."""
        portapapeles(texto="\n")
        app = AppFalsa(prompt=PromptDoble(pegados=0))

        _app()._paste_into_prompt(app)

        assert any("nada" in aviso.lower() for aviso in app.avisos)

    def test_with_the_prompt_closed_it_does_nothing(self, portapapeles):
        portapapeles(texto="algo")
        app = AppFalsa(prompt=PromptDoble(is_open=False))

        _app()._paste_into_prompt(app)

        assert app.text_prompt.recibido is None
        assert app.avisos == []
