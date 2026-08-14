"""
Qué juegos se enseñan según las tiendas marcadas en la configuración.

El ajuste "TIENDAS A CARGAR" decide dos cosas: de qué tiendas se escanea (eso
lo hace el pipeline) y cuáles se ven. Esto último es lo de aquí, y lo aplican
las dos interfaces al pintar.
"""
from dataclasses import dataclass

import pytest

from puntueitor.core.models import Stores
from puntueitor.core.services.library_ops import active_stores, is_in_active_stores


@dataclass
class FakeConfig:
    steam_is_active: bool = True
    gog_is_active: bool = True
    epic_is_active: bool = True
    amazon_is_active: bool = True


class TestActiveStores:
    def test_all(self):
        assert active_stores(FakeConfig()) == {
            Stores.STEAM, Stores.GOG, Stores.EPIC, Stores.AMAZON,
        }

    def test_some(self):
        config = FakeConfig(gog_is_active=False, amazon_is_active=False)
        assert active_stores(config) == {Stores.STEAM, Stores.EPIC}

    def test_none(self):
        config = FakeConfig(False, False, False, False)
        assert active_stores(config) == set()


class TestIsInActiveStores:
    def test_its_store_is_marked(self, make_game):
        game = make_game()
        game.set_store(Stores.STEAM, "1")
        assert is_in_active_stores(game, {Stores.STEAM})

    def test_its_store_is_not(self, make_game):
        game = make_game()
        game.set_store(Stores.GOG, "1")
        assert not is_in_active_stores(game, {Stores.STEAM})

    def test_one_marked_is_enough(self, make_game):
        """
        Un juego que tienes en dos tiendas lo sigues teniendo aunque
        desmarques una: son 82 en la biblioteca real.
        """
        game = make_game()
        game.set_store(Stores.STEAM, "1")
        game.set_store(Stores.EPIC, "abc")

        assert is_in_active_stores(game, {Stores.STEAM})
        assert is_in_active_stores(game, {Stores.EPIC})
        assert not is_in_active_stores(game, {Stores.GOG})

    def test_without_stores_is_always_shown(self, make_game):
        """
        No pertenece a ninguna tienda desmarcada, así que esconderlo sería
        inventarse un criterio que nadie ha pedido.
        """
        assert is_in_active_stores(make_game(), set())

    def test_nothing_marked_hides_everything_with_a_store(self, make_game):
        game = make_game()
        game.set_store(Stores.STEAM, "1")
        assert not is_in_active_stores(game, set())

    def test_no_game(self):
        """Una entrada del carrusel puede no tener ficha."""
        assert is_in_active_stores(None, {Stores.STEAM})


def test_every_store_has_a_config_flag():
    """
    Si mañana se añade una tienda al modelo, este test avisa de que hay que
    darle su interruptor: sin él quedaría siempre escondida.
    """
    todas = active_stores(FakeConfig())
    assert todas == set(Stores)
