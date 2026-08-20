"""Tests de la plantilla común de resolución contra IGDB."""
from unittest.mock import MagicMock

import pytest

from puntueitor.core.models import Stores
from puntueitor.core.resolvers.amazon_resolver import AmazonResolver
from puntueitor.core.resolvers.epic_resolver import EpicResolver
from puntueitor.core.resolvers.gog_resolver import GOGResolver
from puntueitor.core.resolvers.itchio_resolver import ItchioResolver
from puntueitor.core.resolvers.steam_resolver import SteamIGDBResolver

IGDB_GAME = {"id": 99, "name": "Test Game", "genres": []}


@pytest.fixture
def igdb():
    service = MagicMock()
    service.search_by_external_game.return_value = []
    service.search_by_title.return_value = []
    service.search_by_slug.return_value = []
    service.get_game.return_value = IGDB_GAME
    return service


def _resolver(cls, igdb, *, unknown=False, cached=None):
    resolver = cls(igdb=igdb)
    resolver.unknown_cacher = MagicMock()
    resolver.unknown_cacher.is_unknown.return_value = unknown
    resolver.cacher = MagicMock()
    resolver.cacher.available = True
    resolver.cacher.get_igdb_ids.return_value = cached
    return resolver


class TestResolverTemplate:
    def test_resolves_by_external_id_and_tags_store(self, igdb):
        igdb.search_by_external_game.return_value = [IGDB_GAME]
        resolver = _resolver(SteamIGDBResolver, igdb)

        games = resolver.resolve({"appid": 440, "name": "Test Game"})

        assert len(games) == 1
        assert games[0].igdb_id == 99
        assert games[0].stores[Stores.STEAM] == "440"

    def test_uses_cached_mapping_without_searching(self, igdb):
        resolver = _resolver(SteamIGDBResolver, igdb, cached=[99])

        games = resolver.resolve({"appid": 440, "name": "Test Game"})

        assert len(games) == 1
        igdb.search_by_external_game.assert_not_called()
        igdb.search_by_title.assert_not_called()

    def test_known_unknown_game_is_skipped(self, igdb):
        resolver = _resolver(SteamIGDBResolver, igdb, unknown=True)

        assert resolver.resolve({"appid": 440, "name": "Test"}) == []
        igdb.search_by_external_game.assert_not_called()

    def test_not_found_game_is_recorded_as_unknown(self, igdb):
        resolver = _resolver(SteamIGDBResolver, igdb)

        assert resolver.resolve({"appid": 440, "name": "Nope"}) == []
        resolver.unknown_cacher.save_unknown.assert_called_once_with(
            "steam", "Nope", "440"
        )

    def test_missing_store_id_is_skipped(self, igdb):
        resolver = _resolver(GOGResolver, igdb)

        assert resolver.resolve({"title": "Sin id"}) == []
        resolver.unknown_cacher.save_unknown.assert_not_called()

    def test_unavailable_cache_skips_network_lookup(self, igdb):
        resolver = _resolver(SteamIGDBResolver, igdb)
        resolver.cacher.available = False

        assert resolver.resolve({"appid": 440, "name": "Test"}) == []
        igdb.search_by_external_game.assert_not_called()

    def test_short_title_is_not_blacklisted(self, igdb):
        # Un título inservible no debe marcar el juego como desconocido:
        # el problema es el dato de entrada, no que IGDB no lo tenga.
        resolver = _resolver(GOGResolver, igdb)

        assert resolver.resolve({"app_name": "x1", "title": "a"}) == []
        resolver.unknown_cacher.save_unknown.assert_not_called()

    def test_igdb_fetch_failure_skips_game_without_crashing(self, igdb):
        igdb.search_by_external_game.return_value = [IGDB_GAME]
        igdb.get_game.side_effect = RuntimeError("IGDB caído")
        resolver = _resolver(SteamIGDBResolver, igdb)

        assert resolver.resolve({"appid": 440, "name": "Test"}) == []


class TestEpicResolver:
    def test_prefers_slug_lookup(self, igdb):
        igdb.search_by_slug.return_value = [IGDB_GAME]
        resolver = _resolver(EpicResolver, igdb)

        games = resolver.resolve({
            "app_name": "abc",
            "title": "Test Game",
            "store_url": "https://www.epicgames.com/store/product/test-game",
        })

        assert len(games) == 1
        igdb.search_by_slug.assert_called_once_with("test-game", cache_results=True)
        igdb.search_by_title.assert_not_called()

    def test_zero_similarity_candidates_do_not_crash(self, igdb):
        # Antes, si ningún candidato superaba similitud 0.0 el mejor quedaba
        # en None y la traza posterior reventaba con AttributeError.
        igdb.search_by_title.return_value = [
            {"id": 1, "name": "zzzz"},
            {"id": 2, "name": "wwww"},
        ]
        resolver = _resolver(EpicResolver, igdb)

        games = resolver.resolve({"app_name": "abc", "title": "Test Game"})

        assert len(games) == 1


class TestAmazonResolver:
    def test_picks_candidate_closest_to_release_date(self, igdb):
        igdb.search_by_title.return_value = [
            {"id": 1, "name": "Test", "first_release_date": 0},
            {"id": 2, "name": "Test", "first_release_date": 1_600_000_000},
        ]
        igdb.get_game.return_value = {"id": 2, "name": "Test", "genres": []}
        resolver = _resolver(AmazonResolver, igdb)

        games = resolver.resolve({
            "app_name": "amz1",
            "title": "Test",
            "extra": {"releaseDate": "2020-09-14T00:00:00Z"},
        })

        assert games[0].igdb_id == 2

    def test_candidates_without_date_fall_back_to_first(self, igdb):
        igdb.search_by_title.return_value = [{"id": 7, "name": "Test"}]
        igdb.get_game.return_value = {"id": 7, "name": "Test", "genres": []}
        resolver = _resolver(AmazonResolver, igdb)

        games = resolver.resolve({"app_name": "amz1", "title": "Test"})

        assert games[0].igdb_id == 7


class TestItchioResolver:
    """
    itch.io sí se resuelve por id, no solo por título como Amazon: IGDB lo
    indexa como fuente externa nº 30 ("Itchio"), comprobado contra su API real
    y no supuesto por documentación de terceros.
    """

    def test_it_looks_it_up_by_the_external_id_first(self, igdb):
        igdb.search_by_external_game.return_value = [IGDB_GAME]
        resolver = _resolver(ItchioResolver, igdb)

        games = resolver.resolve({"app_name": "583923", "title": "Test Game"})

        igdb.search_by_external_game.assert_called_once_with(
            source_id=30, external_uid="583923", cache_results=True,
        )
        igdb.search_by_title.assert_not_called()
        assert games[0].stores[Stores.ITCHIO] == "583923"

    def test_if_igdb_does_not_have_it_indexed_it_falls_back_to_the_title(self, igdb):
        """
        itch.io tiene cientos de miles de juegos y IGDB no indexa ni de lejos
        todos: sin esta caída, casi toda la biblioteca acabaría en
        Desconocidos.
        """
        igdb.search_by_title.return_value = [IGDB_GAME]
        resolver = _resolver(ItchioResolver, igdb)

        games = resolver.resolve({"app_name": "583923", "title": "Test Game"})

        assert games[0].igdb_id == 99
