"""
Rescatar juegos desconocidos, compartido por la TUI y el carrusel.

En `integration` porque lo que importa es qué queda escrito: sobre todo que un
intento fallido **devuelva el desconocido a su tabla**. Si se pierde ahí, el
juego desaparece de las dos listas y no hay forma de volver a él.

Ningún test toca la red: IGDB y los resolvers van monkeypatcheados.
"""
import pytest

from puntueitor.core import stores
from puntueitor.core.models import Stores
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.services import unknown_actions
from puntueitor.core.services.unknown_actions import (
    SearchResult,
    Unknown,
    adopt_result,
    list_unknowns,
    resolve_by_store,
    search_igdb,
)


@pytest.fixture
def repo(tmp_path) -> LibraryRepository:
    return LibraryRepository(cache_dir=tmp_path)


@pytest.fixture
def unknown(repo) -> Unknown:
    repo.unknown_cacher.save_unknown("steam", "Half-Life 3", "12345")
    return Unknown(store="steam", title="Half-Life 3", id="12345")


@pytest.fixture(autouse=True)
def no_enrichment(monkeypatch):
    """El enriquecido del recién adoptado va a la red: fuera en los tests."""
    monkeypatch.setattr(unknown_actions, "_enrich_new_game", lambda repo, game: game)


RAW = {
    "id": 999,
    "name": "Half-Life 3",
    "first_release_date": 1592179200,   # 2020
    "cover": {"url": "//images.igdb.com/t_thumb/hl3.jpg"},
}


class TestListUnknowns:
    def test_sorted_by_title(self, repo):
        for title, store_id in (("Zelda", "3"), ("anno", "1"), ("Baldur", "2")):
            repo.unknown_cacher.save_unknown("gog", title, store_id)

        titles = [u.title for u in list_unknowns(repo)]

        # Sin distinguir mayúsculas: la tabla no tiene ORDER BY y sale en
        # orden de escaneo, que no le sirve a nadie.
        assert titles == ["anno", "Baldur", "Zelda"]

    def test_maps_the_three_columns(self, repo, unknown):
        got = list_unknowns(repo)[0]
        assert (got.store, got.title, got.id) == ("steam", "Half-Life 3", "12345")
        assert got.key == ("steam", "12345")

    def test_empty(self, repo):
        assert list_unknowns(repo) == []


class TestSearchIgdb:
    def test_maps_results(self, monkeypatch):
        import puntueitor.core.igdb.service as service_mod
        monkeypatch.setattr(
            service_mod.IGDBService, "__init__", lambda self, *a, **k: None,
        )
        monkeypatch.setattr(
            service_mod.IGDBService, "search_by_title",
            lambda self, title, limit=15: [RAW, {"name": "sin id"}],
        )

        results, error = search_igdb("half life")

        assert error is None
        # El que no trae id se descarta: sin él no se puede adoptar.
        assert len(results) == 1
        assert (results[0].igdb_id, results[0].title, results[0].year) == (
            999, "Half-Life 3", 2020,
        )
        assert results[0].raw is RAW

    def test_error_is_returned_not_raised(self, monkeypatch):
        import puntueitor.core.igdb.service as service_mod
        boom = RuntimeError("IGDB caído")

        def explota(self, *a, **k):
            raise boom

        monkeypatch.setattr(service_mod.IGDBService, "__init__", explota)

        results, error = search_igdb("lo que sea")

        assert results == []
        assert error is boom


class TestAdoptResult:
    def test_moves_from_unknown_to_library(self, repo, unknown):
        repo.igdb_cacher.save_game(RAW)

        result = adopt_result(repo, unknown, SearchResult.from_raw(RAW))

        assert result.ok
        assert result.game.igdb_id == 999
        assert result.game.stores[Stores.STEAM] == "12345"
        assert repo.resolvers_cacher.get_stores_for_igdb_id(999) == {"steam": "12345"}
        assert not repo.unknown_cacher.is_unknown("steam", "12345")
        assert repo.load().contains_igdb_id(999)

    def test_bad_store_does_not_raise(self, repo):
        """Una tienda que el modelo no conoce no debe reventar la interfaz."""
        raro = Unknown(store="itch", title="Algo", id="7")

        result = adopt_result(repo, raro, SearchResult.from_raw(RAW))

        assert not result.ok
        assert result.error is not None


class TestCadaTiendaUsaSuResolver:
    """
    Reintentar un desconocido "por su tienda" tiene que lanzar EL resolver de
    esa tienda.

    Esto se despachaba con un if/elif y un `else` que mandaba todo lo demás
    al de GOG: con la llegada de itch.io, sus juegos se buscaban en IGDB por
    la fuente externa equivocada y, si algo llegaba a encajar por título, se
    habría guardado como juego de GOG. La suite entera pasaba igual, porque
    los tests de aquí abajo sustituyen `_store_resolve` por un doble y nadie
    miraba dentro.
    """

    @pytest.fixture
    def sin_igdb(self, monkeypatch):
        """IGDB no se toca: lo que se prueba es a quién se llama."""
        from puntueitor.core.igdb import service

        monkeypatch.setattr(service, "IGDBService", lambda *a, **k: object())

    def _resolver_usado(self, repo, monkeypatch, store, id_juego="1234"):
        usados = []
        from puntueitor.core.resolvers import base_resolver

        monkeypatch.setattr(
            base_resolver.BaseResolver, "resolve",
            lambda self, raw, refresh=False: usados.append((type(self), raw)) or [],
        )
        unknown_actions._store_resolve(
            repo, Unknown(store=store, title="Algo", id=id_juego),
        )
        return usados[0]

    @pytest.mark.parametrize("spec", list(stores.all_stores()), ids=lambda s: s.key)
    def test_the_resolver_is_the_one_the_registry_declares(
        self, spec, repo, monkeypatch, sin_igdb,
    ):
        clase, _ = self._resolver_usado(repo, monkeypatch, spec.key)

        assert clase is spec.resolver()

    @pytest.mark.parametrize("spec", list(stores.all_stores()), ids=lambda s: s.key)
    def test_the_id_reaches_the_resolver_where_it_looks_for_it(
        self, spec, repo, monkeypatch, sin_igdb,
    ):
        """
        Steam llama "appid" a lo que las demás llaman "app_name", y un crudo
        con la clave equivocada deja el id vacío: el juego se descarta sin
        buscarlo siquiera.
        """
        clase, raw = self._resolver_usado(repo, monkeypatch, spec.key, "9876")

        assert clase(igdb=None)._extract_id(raw) == "9876"

    def test_an_unregistered_store_says_so(self, repo, sin_igdb):
        with pytest.raises(ValueError, match="tienda desconocida"):
            unknown_actions._store_resolve(
                repo, Unknown(store="playstation", title="Algo", id="1"),
            )


class TestResolveByStore:
    def _resolver_que(self, monkeypatch, games=None, error=None):
        def fake(repo, unknown):
            if error is not None:
                raise error
            return games or []
        monkeypatch.setattr(unknown_actions, "_store_resolve", fake)

    def test_found(self, repo, unknown, monkeypatch, make_game):
        juego = make_game(igdb_id=999, title="Half-Life 3")
        self._resolver_que(monkeypatch, games=[juego])

        result = resolve_by_store(repo, unknown)

        assert result.ok
        assert result.game is juego
        assert not repo.unknown_cacher.is_unknown("steam", "12345")

    def test_not_found_puts_it_back(self, repo, unknown, monkeypatch):
        """
        Hay que borrarlo ANTES de resolver (el resolver se salta lo marcado
        como desconocido), así que si no se encuentra hay que devolverlo.
        """
        self._resolver_que(monkeypatch, games=[])

        result = resolve_by_store(repo, unknown)

        assert not result.ok
        assert result.error is None
        assert repo.unknown_cacher.is_unknown("steam", "12345")

    def test_error_puts_it_back(self, repo, unknown, monkeypatch):
        boom = RuntimeError("sin red")
        self._resolver_que(monkeypatch, error=boom)

        result = resolve_by_store(repo, unknown)

        assert result.error is boom
        assert repo.unknown_cacher.is_unknown("steam", "12345")

    def test_unsupported_store_is_left_alone(self, repo):
        repo.unknown_cacher.save_unknown("amazon", "Algo", "77")
        raro = Unknown(store="amazon", title="Algo", id="77")

        result = resolve_by_store(repo, raro)

        assert result.unsupported
        assert result.error is None
        # Ni se ha tocado la tabla: no había nada que intentar.
        assert repo.unknown_cacher.is_unknown("amazon", "77")
