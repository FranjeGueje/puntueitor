"""
El cuadro de texto: cómo encoge la letra y cómo pega.

Se prueban `fit_scale` e `insert_at`, que están sueltas a propósito por esto
mismo: montar el `DirectEntry` pediría abrir una ventana de Panda3D.
"""
import pytest

from puntueitor.gui3d.text_prompt import (
    ENTRY_MIN_SCALE,
    ENTRY_SCALE,
    ENTRY_UNITS,
    PANEL_HALF_WIDTH,
    fit_scale,
    insert_at,
    strip_control,
)

#: Lo que cabe a tamaño normal, en unidades de texto.
CUPO = ENTRY_UNITS / ENTRY_SCALE


class TestFitScale:
    def test_empty_text(self):
        assert fit_scale(0) == ENTRY_SCALE

    def test_short_text_keeps_the_normal_size(self):
        """Escribir "Zelda" tiene que verse exactamente como siempre."""
        assert fit_scale(CUPO / 3) == ENTRY_SCALE

    def test_exactly_full(self):
        assert fit_scale(CUPO) == ENTRY_SCALE

    def test_overflowing_text_shrinks_to_fit(self):
        """
        La propiedad que importa: encoge lo justo para que quepa, ni más ni
        menos. `ancho x escala` vuelve a ser el ancho del cuadro.
        """
        escala = fit_scale(CUPO * 1.5)

        assert escala < ENTRY_SCALE
        assert (CUPO * 1.5) * escala == pytest.approx(ENTRY_UNITS)

    def test_never_smaller_than_the_minimum_and_the_text_scrolls_instead(self):
        """
        Un texto absurdo planta la letra: por debajo de ahí no se leería.

        Y ese suelo NO es un tope de escritura — pasado ese punto se sigue
        tecleando y lo que hace el cuadro es deslizar el texto. Eso lo resuelve
        `PGEntry` con `overflow` y no se puede afirmar desde aquí; queda dicho
        en el nombre para que nadie convierta esto otra vez en un límite.
        """
        assert fit_scale(CUPO * 100) == ENTRY_MIN_SCALE

    def test_more_text_never_grows(self):
        anchos = [0, 1, CUPO / 2, CUPO, CUPO * 2, CUPO * 10, CUPO * 1000]
        escalas = [fit_scale(w) for w in anchos]

        assert escalas == sorted(escalas, reverse=True)
        assert all(ENTRY_MIN_SCALE <= e <= ENTRY_SCALE for e in escalas)


class TestConstantes:
    def test_the_box_fits_in_the_panel(self):
        assert ENTRY_UNITS <= 2 * PANEL_HALF_WIDTH

    def test_the_minimum_is_a_minimum(self):
        assert 0 < ENTRY_MIN_SCALE < ENTRY_SCALE

    def test_room_for_a_client_secret(self):
        """
        Los campos de Configuración son el motivo de todo esto: un secret de
        IGDB ronda los 30 caracteres y la carpeta de Heroic pasa de 60. Con la
        fuente de la interfaz, un carácter anda por 0,6 unidades.
        """
        cupo_minimo = ENTRY_UNITS / ENTRY_MIN_SCALE
        assert cupo_minimo / 0.6 >= 80


class TestInsertAt:
    """
    Pegar mete el texto donde está el cursor, no reemplaza lo escrito.

    En el caso que motivó esto —pegar la URL del login en un cuadro vacío—
    las dos cosas darían igual; insertar es lo que se porta bien el resto de
    las veces.
    """

    def test_into_an_empty_field(self):
        assert insert_at("", "https://x", 0) == ("https://x", 9)

    def test_at_the_end(self):
        assert insert_at("abc", "XY", 3) == ("abcXY", 5)

    def test_at_the_start(self):
        assert insert_at("abc", "XY", 0) == ("XYabc", 2)

    def test_in_the_middle(self):
        assert insert_at("abc", "XY", 1) == ("aXYbc", 3)

    def test_the_cursor_lands_after_what_was_pasted(self):
        texto, cursor = insert_at("hola", "MUNDO", 2)
        assert texto[:cursor].endswith("MUNDO")

    def test_a_cursor_out_of_range_pastes_at_the_end(self):
        """No puede romper nada, y al final es lo que se esperaría."""
        assert insert_at("abc", "X", 99) == ("abcX", 4)
        assert insert_at("abc", "X", -1) == ("abcX", 4)

    def test_pasting_nothing_changes_nothing(self):
        assert insert_at("abc", "", 1) == ("abc", 1)

    def test_newlines_do_not_get_in(self):
        """
        El cuadro es de una línea: un salto no se vería, pero viajaría dentro
        de la URL al canjear el código.
        """
        assert insert_at("", "https://x\n", 0) == ("https://x", 9)
        assert insert_at("", "a\r\nb", 0) == ("ab", 2)

    def test_the_control_character_of_ctrl_v_does_not_get_in(self):
        """
        Algunos toolkits mandan 0x16 al pulsar Ctrl-V además de disparar el
        evento. Colado dentro de una URL sería invisible y la tienda
        rechazaría el código sin que se pudiera ver por qué.
        """
        assert insert_at("", "\x16https://x", 0) == ("https://x", 9)

    def test_something_that_is_only_control_characters_is_nothing(self):
        assert insert_at("abc", "\n\n", 3) == ("abc", 3)


class TestStripControl:
    """
    Lo que sale del cuadro va limpio, entrara por donde entrara.

    No basta con limpiar lo que se pega: si el `DirectEntry` llegara a meter
    por su cuenta el carácter de control del Ctrl-V, se colaría dentro de la
    URL sin verse y la tienda rechazaría el código sin explicación posible.
    """

    def test_the_ctrl_v_control_character(self):
        assert strip_control("https://x\x16") == "https://x"

    def test_newlines_and_tabs(self):
        assert strip_control("a\nb\tc\r") == "abc"

    def test_normal_text_is_left_alone(self):
        assert strip_control("https://x/?a=1&b=2") == "https://x/?a=1&b=2"

    def test_accents_are_not_control_characters(self):
        assert strip_control("añó") == "añó"

    def test_nothing(self):
        assert strip_control("") == ""
        assert strip_control(None) == ""
