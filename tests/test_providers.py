"""
La política común de los proveedores de tienda.

Lo que se prueba aquí no es ninguna API concreta —ninguna prueba toca la
red—, sino la regla que las cuatro comparten: de dónde salen los juegos
cuando la web contesta, cuando no contesta y cuando no hay sesión.
"""
import logging

import pytest

from puntueitor.core.cachers.store_library_cacher import StoreLibraryCacher
from puntueitor.core.models import Stores
from puntueitor.core.providers.base import LibraryProvider


class FakeProvider(LibraryProvider):
    """Un proveedor de mentira: se le dice qué contestar y si falla."""

    STORE = Stores.GOG
    LABEL = "Tienda"

    def __init__(self, juegos=None, error=None, listo=True, **kwargs):
        super().__init__(**kwargs)
        self.juegos = juegos if juegos is not None else []
        self.error = error
        self.listo = listo
        self.llamadas = 0

    def is_ready(self):
        return (True, "") if self.listo else (False, "no has iniciado sesión")

    def _fetch_remote(self):
        self.llamadas += 1
        if self.error:
            raise self.error
        return self.juegos

    @staticmethod
    def store_id(raw):
        return str(raw.get("app_name") or "")


PORTAL = {"app_name": "400", "title": "Portal"}
PORTAL2 = {"app_name": "620", "title": "Portal 2"}


class TestCaminoFeliz:
    def test_fetches_and_caches(self):
        provider = FakeProvider([PORTAL])

        assert provider.fetch(refresh=True) == [PORTAL]
        assert StoreLibraryCacher("gog").get_games() == [PORTAL]

    def test_without_refresh_the_cache_is_enough(self):
        FakeProvider([PORTAL]).fetch(refresh=True)

        segundo = FakeProvider([PORTAL2])
        assert segundo.fetch(refresh=False) == [PORTAL]
        assert segundo.llamadas == 0, "no debía haber llamado a la tienda"

    def test_refresh_goes_to_the_store_again(self):
        FakeProvider([PORTAL]).fetch(refresh=True)

        segundo = FakeProvider([PORTAL2])
        assert segundo.fetch(refresh=True) == [PORTAL2]
        assert segundo.llamadas == 1

    def test_empty_cache_forces_the_call(self):
        """La primera vez no hay copia, así que se llama aunque no se refresque."""
        provider = FakeProvider([PORTAL])

        assert provider.fetch(refresh=False) == [PORTAL]
        assert provider.llamadas == 1


class TestSinConexion:
    def test_falls_back_to_the_cache(self, caplog):
        FakeProvider([PORTAL]).fetch(refresh=True)

        caido = FakeProvider(error=ConnectionError("boom"))
        with caplog.at_level(logging.WARNING):
            assert caido.fetch(refresh=True) == [PORTAL]

        assert "Tienda" in caplog.text

    def test_without_cache_returns_nothing_but_says_why(self, caplog):
        caido = FakeProvider(error=ConnectionError("boom"))

        with caplog.at_level(logging.WARNING):
            assert list(caido.fetch(refresh=True)) == []

        assert "copia guardada" in caplog.text

    def test_a_failure_does_not_destroy_the_cache(self):
        FakeProvider([PORTAL]).fetch(refresh=True)
        FakeProvider(error=ConnectionError("boom")).fetch(refresh=True)

        assert StoreLibraryCacher("gog").get_games() == [PORTAL]


class TestSesionCaducada:
    def test_not_ready_uses_the_cache(self, caplog):
        FakeProvider([PORTAL]).fetch(refresh=True)

        sin_sesion = FakeProvider(listo=False)
        with caplog.at_level(logging.WARNING):
            assert sin_sesion.fetch(refresh=True) == [PORTAL]

        assert "no has iniciado sesión" in caplog.text
        assert sin_sesion.llamadas == 0, "no se llama a una tienda sin sesión"

    def test_not_ready_without_cache_is_empty(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert list(FakeProvider(listo=False).fetch(refresh=True)) == []


class TestRespuestaVacia:
    def test_an_empty_answer_keeps_the_previous_library(self, caplog):
        """
        Que una tienda conteste "cero juegos" casi nunca significa que hayas
        vendido la cuenta; lo normal es que se le haya caducado algo. Tirar
        la copia buena por eso deja al usuario sin biblioteca.
        """
        FakeProvider([PORTAL]).fetch(refresh=True)

        vacia = FakeProvider([])
        with caplog.at_level(logging.WARNING):
            assert vacia.fetch(refresh=True) == [PORTAL]

    def test_games_without_id_are_skipped(self):
        provider = FakeProvider([PORTAL, {"title": "Sin identificador"}])
        provider.fetch(refresh=True)

        assert StoreLibraryCacher("gog").get_games() == [PORTAL]


def test_fetch_never_raises():
    """
    Vale para cualquier fallo, no solo los de red: `load_library` recorre las
    cuatro tiendas seguidas y una que reventara se llevaría por delante las
    que vienen detrás.
    """
    assert list(FakeProvider(error=ValueError("cualquier cosa")).fetch()) == []
