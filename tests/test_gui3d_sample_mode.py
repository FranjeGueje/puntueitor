"""
Los seis juegos de ejemplo se van en cuanto llega la biblioteca de verdad.

El carrusel enseña ejemplos (Hollow Knight y compañía) cuando no hay nada que
enseñar, y eso está bien. Lo que estaba mal es que se quedaban: al recargar,
los juegos reales se añadían ENCIMA y quedaban los seis falsos mezclados con
los de verdad hasta reiniciar la aplicación.

`_on_game_refreshed` y `_persist_flags` solo miran atributos, así que se les
puede llamar con un objeto de mentira por `self` y sin abrir ninguna ventana
—mismo patrón que `test_gui3d_paste.py`—. `build_sample_entries` no se toca
aquí porque crea texturas y esas sí necesitan Panda3D.
"""
import pytest


class CarruselDoble:
    def __init__(self):
        self.vaciados = 0
        self.reetiquetados = []

    def clear(self):
        self.vaciados += 1

    def rebuild_labels(self, key, game, visible):
        self.reetiquetados.append(key)


class CacherDoble:
    def __init__(self):
        self.escrituras = []

    def set_status(self, igdb_id, **estados):
        self.escrituras.append(igdb_id)


class Entrada:
    def __init__(self, key, game=None):
        self.key = key
        self.game = game


class AppFalsa:
    """Lo que miran los dos métodos que se prueban."""

    def __init__(self, sample_mode=True, entries=None):
        self._sample_mode = sample_mode
        self.entries = list(entries or [])
        self.carousel = CarruselDoble()
        self._pending_covers = set()
        self._labels_visible = True
        self._refresh_added = 0
        self.anadidos = []
        self.avisos = []
        self.notifier = type(
            "N", (), {"show": lambda _s, m: self.avisos.append(m)},
        )()
        self.library_repository = type(
            "R", (), {"library_cacher": CacherDoble()},
        )()

    # Los de verdad, para que el test cubra el camino entero
    def _clear_carousel(self):
        from puntueitor.gui3d.app import App

        App._clear_carousel(self)

    def _on_selection_changed(self):
        pass

    def _add_game_entry(self, game):
        self.anadidos.append(game.igdb_id)
        self.entries.append(Entrada(game.igdb_id, game))


def _refrescar(app, game):
    from puntueitor.gui3d.app import App

    return App._on_game_refreshed(app, game)


@pytest.fixture
def juego(make_game):
    return make_game


class TestSePurganLosEjemplos:
    def test_the_first_real_game_wipes_them(self, juego):
        """
        Seis cajas de mentira en pantalla y llega el primer juego real: fuera
        las seis.
        """
        app = AppFalsa(entries=[Entrada(i) for i in range(6)])

        _refrescar(app, juego(igdb_id=1234, title="Half-Life", cover_url="u"))

        assert app.carousel.vaciados == 1
        assert not app._sample_mode
        assert app.anadidos == [1234]
        # Solo queda el de verdad: los seis se fueron con el vaciado.
        assert [e.key for e in app.entries] == [1234]

    def test_the_second_game_does_not_wipe_again(self, juego):
        """
        Si cada juego vaciara, se borraría el anterior y acabaría entrando
        uno solo — que es peor que el fallo que se está arreglando.
        """
        app = AppFalsa(entries=[Entrada(i) for i in range(6)])

        _refrescar(app, juego(igdb_id=1, title="Uno", cover_url="u"))
        _refrescar(app, juego(igdb_id=2, title="Dos", cover_url="u"))

        assert app.carousel.vaciados == 1
        assert app.anadidos == [1, 2]

    def test_a_normal_refresh_never_wipes(self, juego):
        """
        Con biblioteca de verdad no se vacía nada: la recarga dura minutos y
        dejar la pantalla en blanco mientras tanto sería un fallo peor.
        """
        app = AppFalsa(sample_mode=False, entries=[Entrada(99)])

        _refrescar(app, juego(igdb_id=1234, title="Half-Life", cover_url="u"))

        assert app.carousel.vaciados == 0
        assert [e.key for e in app.entries] == [99, 1234]

    def test_the_wipe_happens_before_deduplicating(self, juego):
        """
        Los ejemplos usan `igdb_id` 0-5, que IGDB también usa de verdad. Si
        se purgara después de buscar duplicados, un juego real con uno de
        esos ids se tomaría por una entrada de ejemplo: se le pisarían los
        datos al muñeco y el juego se quedaría sin caja.
        """
        app = AppFalsa(entries=[Entrada(i) for i in range(6)])

        nuevo = _refrescar(app, juego(igdb_id=3, title="De verdad", cover_url="u"))

        assert nuevo, "tenía que entrar como juego nuevo, no como duplicado"
        assert app.anadidos == [3]
        assert app.carousel.reetiquetados == [], "no debía tocar ningún muñeco"
        assert [e.key for e in app.entries] == [3]

    def test_a_game_without_a_cover_still_wipes_them(self, juego):
        """
        Un juego sin carátula no entra en el carrusel, pero significa igual
        que la biblioteca de verdad ya está llegando.
        """
        app = AppFalsa(entries=[Entrada(i) for i in range(6)])

        assert not _refrescar(
            app, juego(igdb_id=7, title="Sin carátula", cover_url=None),
        )
        assert app.carousel.vaciados == 1
        assert app.entries == []


class TestNoSeGuardanEstadosFalsos:
    """
    Marcar un juego de ejemplo escribía una fila real en `library.sqlite`
    con `igdb_id` 0-5. No estorbaba al pintar, pero se quedaba para siempre
    en la única base de datos que NO se puede regenerar.
    """

    @staticmethod
    def _guardar(app, game):
        from puntueitor.gui3d.app import App

        App._persist_flags(app, game)

    def test_nothing_is_written_in_sample_mode(self, juego):
        app = AppFalsa()

        self._guardar(app, juego(igdb_id=3, title="Hollow Knight"))

        assert app.library_repository.library_cacher.escrituras == []

    def test_it_says_why_instead_of_failing_in_silence(self, juego):
        app = AppFalsa()

        self._guardar(app, juego(igdb_id=3, title="Hollow Knight"))

        assert any("ejemplo" in aviso for aviso in app.avisos)

    def test_real_games_are_written(self, juego):
        app = AppFalsa(sample_mode=False)

        self._guardar(app, juego(igdb_id=1234, title="Half-Life"))

        assert app.library_repository.library_cacher.escrituras == [1234]
