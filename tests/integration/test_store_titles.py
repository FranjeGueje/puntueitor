"""
Recuperar el nombre que un juego tiene en su tienda.

En `integration` porque lee de verdad las fuentes de cada tienda: la caché
SQLite de Steam y los ficheros de biblioteca de Heroic, aquí montados en un
`tmp_path`.
"""
import json
from dataclasses import dataclass

import pytest

from puntueitor.core.cachers.steam_user_cacher import SteamUserCacher
from puntueitor.core.services.store_titles import store_title


@dataclass
class FakeConfig:
    """Lo único que `store_title` mira de la configuración."""

    steam_user_id: int | str = ""
    heroic_path: str = ""


@pytest.fixture
def heroic(tmp_path) -> FakeConfig:
    """Una carpeta de Heroic con las tres bibliotecas escritas."""
    store_cache = tmp_path / "heroic" / "store_cache"
    store_cache.mkdir(parents=True)
    ficheros = {
        "gog_library.json": [
            {"app_name": "1207658893", "title": "Baldur's Gate 2 Complete"},
        ],
        "legendary_library.json": [
            {"app_name": "BatfishS2", "title": "Telltale Batman Season 2"},
        ],
        "nile_library.json": [
            {"app_name": "c7827e1e", "title": "Samurai Shodown V Special"},
        ],
    }
    for nombre, juegos in ficheros.items():
        (store_cache / nombre).write_text(json.dumps({"games": juegos}))
    return FakeConfig(heroic_path=str(tmp_path / "heroic"))


class TestHeroicStores:
    @pytest.mark.parametrize("store,store_id,esperado", [
        ("gog", "1207658893", "Baldur's Gate 2 Complete"),
        ("epic", "BatfishS2", "Telltale Batman Season 2"),
        ("amazon", "c7827e1e", "Samurai Shodown V Special"),
    ])
    def test_finds_the_title(self, heroic, store, store_id, esperado):
        assert store_title(store, store_id, heroic) == esperado

    def test_unknown_id(self, heroic):
        assert store_title("gog", "no-existe", heroic) is None

    def test_each_store_reads_its_own_file(self, heroic):
        """Un id de Epic no debe encontrarse buscando en GOG."""
        assert store_title("gog", "BatfishS2", heroic) is None

    def test_without_heroic_installed(self, tmp_path):
        vacio = FakeConfig(heroic_path=str(tmp_path / "no-esta"))
        assert store_title("gog", "1207658893", vacio) is None

    def test_broken_json_does_not_raise(self, tmp_path):
        store_cache = tmp_path / "heroic" / "store_cache"
        store_cache.mkdir(parents=True)
        (store_cache / "gog_library.json").write_text("{esto no es json")
        config = FakeConfig(heroic_path=str(tmp_path / "heroic"))
        assert store_title("gog", "1207658893", config) is None


class TestSteam:
    def test_finds_the_name(self):
        # Sin `cache_dir`, `SteamUserCacher` va a `paths.cache_dir()`, que en
        # los tests ya apunta al sandbox de `conftest` — y es la ruta que
        # usará `store_title`, que no recibe directorios.
        SteamUserCacher(123).save_games([{"appid": 400, "name": "Portal"}])

        assert store_title("steam", "400", FakeConfig(steam_user_id=123)) == "Portal"

    def test_id_as_text_or_number(self, tmp_path):
        """En `resolvers` los ids son texto y en la caché de Steam, enteros."""
        SteamUserCacher(456).save_games([{"appid": 620, "name": "Portal 2"}])
        config = FakeConfig(steam_user_id=456)
        assert store_title("steam", "620", config) == "Portal 2"
        assert store_title("steam", 620, config) == "Portal 2"

    def test_without_user_id(self):
        assert store_title("steam", "400", FakeConfig()) is None

    def test_empty_cache(self):
        assert store_title("steam", "400", FakeConfig(steam_user_id=999)) is None


def test_unsupported_store():
    assert store_title("itch", "algo", FakeConfig()) is None
