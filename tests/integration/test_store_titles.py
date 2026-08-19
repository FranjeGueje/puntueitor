"""
Recuperar el nombre que un juego tiene en su tienda.

En `integration` porque lee de verdad la caché de bibliotecas
(`StoreLibraryCacher`), la misma SQLite de la que come el pipeline, aquí
dentro del sandbox de `conftest`.
"""
import pytest

from puntueitor.core.cachers.store_library_cacher import StoreLibraryCacher
from puntueitor.core.services.store_titles import store_title


def _guardar(store: str, juegos: list[dict]) -> None:
    """Deja `juegos` en la caché de `store`, como haría su proveedor."""
    StoreLibraryCacher(store).save_games(
        juegos,
        id_of=lambda raw: raw.get("app_name") or raw.get("appid"),
        title_of=lambda raw: raw.get("title") or raw.get("name"),
    )


@pytest.fixture
def bibliotecas():
    """Las cuatro tiendas con un juego cada una."""
    _guardar("gog", [{"app_name": "1207658893", "title": "Baldur's Gate 2 Complete"}])
    _guardar("epic", [{"app_name": "BatfishS2", "title": "Telltale Batman Season 2"}])
    _guardar("amazon", [{"app_name": "c7827e1e", "title": "Samurai Shodown V Special"}])
    _guardar("steam", [{"appid": 400, "name": "Portal"}])


class TestTitulos:
    @pytest.mark.parametrize("store,store_id,esperado", [
        ("gog", "1207658893", "Baldur's Gate 2 Complete"),
        ("epic", "BatfishS2", "Telltale Batman Season 2"),
        ("amazon", "c7827e1e", "Samurai Shodown V Special"),
        ("steam", "400", "Portal"),
    ])
    def test_finds_the_title(self, bibliotecas, store, store_id, esperado):
        assert store_title(store, store_id) == esperado

    def test_unknown_id(self, bibliotecas):
        assert store_title("gog", "no-existe") is None

    def test_each_store_reads_its_own_games(self, bibliotecas):
        """Un id de Epic no debe encontrarse buscando en GOG."""
        assert store_title("gog", "BatfishS2") is None

    def test_id_as_text_or_number(self, bibliotecas):
        """En `resolvers` los ids son texto y en la tienda pueden ser enteros."""
        assert store_title("steam", 400) == "Portal"

    def test_empty_cache(self):
        assert store_title("steam", "400") is None

    def test_unsupported_store(self):
        assert store_title("itch", "algo") is None


class TestCache:
    def test_refresh_replaces_the_previous_library(self):
        """Un juego que ya no está en la tienda desaparece de la caché."""
        _guardar("gog", [{"app_name": "1", "title": "Antiguo"}])
        _guardar("gog", [{"app_name": "2", "title": "Nuevo"}])

        assert store_title("gog", "1") is None
        assert store_title("gog", "2") == "Nuevo"

    def test_a_store_does_not_wipe_the_others(self):
        _guardar("gog", [{"app_name": "1", "title": "GOG uno"}])
        _guardar("epic", [{"app_name": "2", "title": "Epic dos"}])

        assert store_title("gog", "1") == "GOG uno"
        assert store_title("epic", "2") == "Epic dos"

    def test_empty_save_keeps_the_previous_copy(self):
        """
        Una tienda que contesta sin juegos no puede borrar lo que ya tenías:
        es casi siempre un fallo suyo, no que hayas vendido la cuenta.
        """
        _guardar("gog", [{"app_name": "1", "title": "Sigue ahí"}])
        _guardar("gog", [])

        assert store_title("gog", "1") == "Sigue ahí"
