"""
El cuadro de texto encoge la letra en vez de cortar lo escrito.

Solo se prueba `fit_scale`, que es la única aritmética y está suelta a
propósito: montar el `DirectEntry` pediría abrir una ventana de Panda3D.
"""
import pytest

from puntueitor.gui3d.text_prompt import (
    ENTRY_MIN_SCALE,
    ENTRY_SCALE,
    ENTRY_UNITS,
    PANEL_HALF_WIDTH,
    fit_scale,
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
