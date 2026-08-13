"""
Las dos acciones sobre un juego suelto, compartidas por la TUI y el carrusel.

Van en `integration` porque tocan las bases de datos de verdad (en un
`tmp_path`): lo que se comprueba de `forget_game` es justamente qué queda
escrito y qué deja de estarlo.
"""
import pytest

from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.services import game_actions
from puntueitor.core.services.game_actions import enrich_game, forget_game


@pytest.fixture
def repo(tmp_path) -> LibraryRepository:
    return LibraryRepository(cache_dir=tmp_path)


class TestForgetGame:
    def test_removes_mapping_and_records_unknown(self, repo, make_game):
        game = make_game(igdb_id=1001, title="Test Game")
        repo.resolvers_cacher.set_igdb_ids("steam", "12345", [1001])
        repo.resolvers_cacher.set_igdb_ids("gog", "999", [1001])

        stores = forget_game(repo, game)

        assert stores == {"steam": "12345", "gog": "999"}
        assert repo.resolvers_cacher.get_stores_for_igdb_id(1001) is None
        assert repo.unknown_cacher.is_unknown("steam", "12345")
        assert repo.unknown_cacher.is_unknown("gog", "999")

    def test_game_disappears_from_library(self, repo, make_game):
        game = make_game(igdb_id=1001)
        repo.resolvers_cacher.set_igdb_ids("steam", "12345", [1001])
        repo.igdb_cacher.save_game({"id": 1001, "name": "Test Game"})
        assert len(repo.load()) == 1

        forget_game(repo, game)

        assert len(repo.load()) == 0

    def test_without_stores_does_nothing_bad(self, repo, make_game):
        """Un juego que no está en ninguna tienda no revienta ni inventa."""
        assert forget_game(repo, make_game(igdb_id=1001)) == {}
        assert repo.unknown_cacher.count() == 0


class _FakeEnricher:
    """Enricher de mentira: devuelve lo que se le diga, o revienta."""

    def __init__(self, result=None, error=None, **kwargs):
        self._result = result
        self._error = error

    def enrich(self, game):
        if self._error is not None:
            raise self._error
        return self._result if self._result is not None else game


def _patch_enrichers(monkeypatch, *, hltb=None, steam=None):
    """
    Sustituye los dos enrichers EN SU MÓDULO DE ORIGEN.

    Hay que parchearlos ahí y no en `game_actions` porque este los importa
    dentro de la función, no al cargar el módulo: cuando el test corre,
    `game_actions` todavía no tiene ningún nombre al que apuntar.
    """
    import puntueitor.core.enrichers.hltb_enricher as hltb_mod
    import puntueitor.core.enrichers.steam_score_enricher as steam_mod
    import puntueitor.core.resolvers.hltb_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "HLTBResolver", lambda *a, **k: object())
    monkeypatch.setattr(
        hltb_mod, "HLTBEnricher", lambda **k: hltb or _FakeEnricher(),
    )
    monkeypatch.setattr(
        steam_mod, "SteamScoreEnricher", lambda **k: steam or _FakeEnricher(),
    )


class TestEnrichGame:
    def test_found_persists_extras(self, repo, make_game, monkeypatch):
        game = make_game(igdb_id=1001, duration_hours=None, steamdb_score=None)
        enriched = make_game(igdb_id=1001, duration_hours=42.0, steamdb_score=None)
        _patch_enrichers(monkeypatch, steam=_FakeEnricher(result=enriched))

        result = enrich_game(repo, game)

        assert result.ok
        assert result.found
        assert result.game.duration_hours == 42.0
        assert repo.extras_cacher.get_extras(1001)["duration_hours"] == 42.0

    def test_nothing_found_saves_nothing(self, repo, make_game, monkeypatch):
        """Sin datos NO se escribe: una fila de extras a nulos no aporta."""
        empty = make_game(
            igdb_id=1001, duration_hours=None, steam_review=None,
            steamdb_score=None, review_pos=None, review_neg=None,
        )
        _patch_enrichers(monkeypatch, steam=_FakeEnricher(result=empty))

        result = enrich_game(repo, empty)

        assert result.ok
        assert not result.found
        assert not repo.extras_cacher.get_extras(1001)

    def test_error_is_returned_not_raised(self, repo, make_game, monkeypatch):
        """
        La red se cae constantemente, y quien llama está dentro de un hilo:
        una excepción ahí se perdería sin dejar rastro, así que vuelve dentro
        del resultado.
        """
        boom = RuntimeError("sin red")
        _patch_enrichers(monkeypatch, hltb=_FakeEnricher(error=boom))

        result = enrich_game(repo, make_game(igdb_id=1001))

        assert not result.ok
        assert result.error is boom
        assert not result.found
        assert not repo.extras_cacher.get_extras(1001)

    def test_enriched_fields_match_the_repository(self):
        """
        Los campos que deciden si "hubo datos" tienen que ser extras de
        verdad; si un día se añade uno nuevo a la tabla, este test avisa de
        que hay que mirar si también cuenta aquí.
        """
        from puntueitor.core.repository.library_repository import EXTRA_FIELDS
        assert set(game_actions._ENRICHED_FIELDS) <= set(EXTRA_FIELDS)
