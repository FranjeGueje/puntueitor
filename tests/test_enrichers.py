from unittest.mock import Mock, patch, MagicMock
from dataclasses import replace

import pytest

from puntueitor.core.enrichers.hltb_enricher import HLTBEnricher, HLTBClient
from puntueitor.core.enrichers.steam_score_enricher import SteamScoreEnricher
from puntueitor.core.raw.howlongtobeat.hltb_entry import HLTBEntry
from puntueitor.core.models import Game, Stores


# ── HLTB Enricher ──────────────────────────────────────────────

class MockHLTBClient(HLTBClient):
    def __init__(self, entry: HLTBEntry | None = None):
        self._entry = entry

    def search(self, title: str) -> HLTBEntry | None:
        return self._entry


SAMPLE_HLTB_ENTRY = HLTBEntry(
    hltb_id=42,
    name="Test Game",
    main_story=15.0,
    main_extra=20.0,
    completionist=50.0,
    similarity=0.95,
    url="https://howlongtobeat.com/game/42",
)


class TestHLTBEnricher:
    def test_enrich_with_valid_entry(self):
        g = Game(igdb_id=1, title="Test Game")
        client = MockHLTBClient(SAMPLE_HLTB_ENTRY)
        enricher = HLTBEnricher(client=client)
        result = enricher.enrich(g)
        assert result.duration_hours == 15.0

    def test_uses_main_story_before_main_extra(self):
        g = Game(igdb_id=1, title="Test Game")
        client = MockHLTBClient(SAMPLE_HLTB_ENTRY)
        enricher = HLTBEnricher(client=client)
        result = enricher.enrich(g)
        assert result.duration_hours == SAMPLE_HLTB_ENTRY.main_story

    def test_fallback_to_main_extra(self):
        entry = HLTBEntry(
            hltb_id=42, name="Test", main_story=None,
            main_extra=25.0, completionist=None,
            similarity=0.95, url=None,
        )
        client = MockHLTBClient(entry)
        enricher = HLTBEnricher(client=client)
        g = Game(igdb_id=1, title="Test")
        result = enricher.enrich(g)
        assert result.duration_hours == 25.0

    def test_no_entry_leaves_duration_unknown(self):
        # "No encontrado" es None (desconocido), nunca 0: un 0 haría que los
        # scorers lo tratasen como un juego que dura cero horas.
        g = Game(igdb_id=1, title="Test Game")
        client = MockHLTBClient(None)
        enricher = HLTBEnricher(client=client)
        result = enricher.enrich(g)
        assert result.duration_hours is None

    def test_low_similarity_leaves_duration_unknown(self):
        entry = HLTBEntry(
            hltb_id=42, name="Different", main_story=10.0,
            main_extra=None, completionist=None,
            similarity=0.3, url=None,
        )
        client = MockHLTBClient(entry)
        enricher = HLTBEnricher(client=client, min_similarity=0.6)
        g = Game(igdb_id=1, title="Test")
        result = enricher.enrich(g)
        assert result.duration_hours is None

    def test_overwrite_flag(self):
        g = Game(igdb_id=1, title="Test", duration_hours=10.0)
        client = MockHLTBClient(SAMPLE_HLTB_ENTRY)
        enricher = HLTBEnricher(client=client, overwrite=False)
        result = enricher.enrich(g)
        assert result.duration_hours == 10.0  # unchanged

        enricher2 = HLTBEnricher(client=client, overwrite=True)
        result2 = enricher2.enrich(g)
        assert result2.duration_hours == 15.0  # overwritten

    def test_assertion_on_bad_similarity(self):
        client = MockHLTBClient(SAMPLE_HLTB_ENTRY)
        with pytest.raises(AssertionError):
            HLTBEnricher(client=client, min_similarity=-0.1)
        with pytest.raises(AssertionError):
            HLTBEnricher(client=client, min_similarity=1.5)

    def test_exception_in_search_returns_original(self, make_game):
        g = make_game(duration_hours=None)
        class BrokenClient(HLTBClient):
            def search(self, title):
                raise RuntimeError("API down")
        enricher = HLTBEnricher(client=BrokenClient())
        result = enricher.enrich(g)
        assert result.duration_hours is None

    def test_none_duration_leaves_duration_unknown(self):
        entry = HLTBEntry(
            hltb_id=42, name="Test", main_story=None,
            main_extra=None, completionist=None,
            similarity=0.95, url=None,
        )
        client = MockHLTBClient(entry)
        enricher = HLTBEnricher(client=client)
        g = Game(igdb_id=1, title="Test")
        result = enricher.enrich(g)
        assert result.duration_hours is None

    def test_zero_duration_leaves_duration_unknown(self):
        entry = HLTBEntry(
            hltb_id=42, name="Test", main_story=0.0,
            main_extra=None, completionist=None,
            similarity=0.95, url=None,
        )
        client = MockHLTBClient(entry)
        enricher = HLTBEnricher(client=client)
        g = Game(igdb_id=1, title="Test")
        result = enricher.enrich(g)
        assert result.duration_hours is None

    def test_failed_lookup_is_recorded_to_avoid_retrying(self):
        from unittest.mock import MagicMock
        cacher = MagicMock()
        cacher.is_hltb_checked.return_value = False
        client = MockHLTBClient(None)
        enricher = HLTBEnricher(client=client, extras_cacher=cacher)

        enricher.enrich(Game(igdb_id=7, title="Test"))
        cacher.mark_hltb_checked.assert_called_once_with(7)

    def test_already_checked_game_is_not_searched_again(self):
        from unittest.mock import MagicMock
        cacher = MagicMock()
        cacher.is_hltb_checked.return_value = True

        class ExplodingClient(HLTBClient):
            def search(self, title):
                raise AssertionError("no debería consultarse HLTB de nuevo")

        enricher = HLTBEnricher(client=ExplodingClient(), extras_cacher=cacher)
        result = enricher.enrich(Game(igdb_id=7, title="Test"))
        assert result.duration_hours is None

    def test_transient_error_is_not_recorded_as_checked(self):
        from unittest.mock import MagicMock
        cacher = MagicMock()
        cacher.is_hltb_checked.return_value = False

        class BrokenClient(HLTBClient):
            def search(self, title):
                raise RuntimeError("API down")

        enricher = HLTBEnricher(client=BrokenClient(), extras_cacher=cacher)
        enricher.enrich(Game(igdb_id=7, title="Test"))
        cacher.mark_hltb_checked.assert_not_called()

    def test_does_not_mutate_original(self):
        g = Game(igdb_id=1, title="Test Game")
        original_id = id(g)
        client = MockHLTBClient(SAMPLE_HLTB_ENTRY)
        enricher = HLTBEnricher(client=client)
        result = enricher.enrich(g)
        assert result is not g
        assert id(g) == original_id


# ── Steam Score Enricher ────────────────────────────────────────

class TestSteamScoreEnricher:
    def test_skip_if_already_enriched(self, make_game):
        g = make_game(steamdb_score=80.0, steam_review=7)
        enricher = SteamScoreEnricher(igdb_cacher=None)
        result = enricher.enrich(g)
        assert result.steamdb_score == 80.0

    def test_overwrite_when_forced(self, make_game):
        g = make_game(steamdb_score=80.0, steam_review=7,
                      stores={"steam": "12345"})
        with patch.object(SteamScoreEnricher, "_fetch_score") as mock_fetch:
            mock_fetch.return_value = (90.0, 8, 5000, 200)
            enricher = SteamScoreEnricher(overwrite=True)
            result = enricher.enrich(g)
            assert result.steamdb_score == 90.0

    def test_no_steam_id_returns_unchanged(self):
        g = Game(igdb_id=1, title="Test")
        enricher = SteamScoreEnricher(igdb_cacher=None)
        result = enricher.enrich(g)
        assert result.steamdb_score is None

    def test_steam_id_from_stores(self):
        g = Game(igdb_id=1, title="Test", stores={"steam": "12345"})
        enricher = SteamScoreEnricher(igdb_cacher=None)
        sid = enricher._get_steam_id(g)
        assert sid == "12345"

    def test_steam_id_from_igdb_cacher(self):
        g = Game(igdb_id=1, title="Test", stores={})
        mock_cacher = MagicMock()
        mock_cacher.get_game.return_value = {"steam_id": 99999}
        enricher = SteamScoreEnricher(igdb_cacher=mock_cacher)
        sid = enricher._get_steam_id(g)
        assert sid == "99999"

    def test_steam_id_not_found(self):
        g = Game(igdb_id=1, title="Test")
        mock_cacher = MagicMock()
        mock_cacher.get_game.return_value = {}
        enricher = SteamScoreEnricher(igdb_cacher=mock_cacher)
        sid = enricher._get_steam_id(g)
        assert sid is None

    def test_fetch_score_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query_summary": {
                "total_positive": 900,
                "total_negative": 100,
                "total_reviews": 1000,
                "review_score": 8,
            }
        }
        enricher = SteamScoreEnricher()
        with patch("requests.get", return_value=mock_response):
            steamdb, review, pos, neg = enricher._fetch_score("12345")
            assert steamdb is not None
            assert 0 < steamdb < 100
            assert review == 8
            assert pos == 900
            assert neg == 100

    def test_fetch_score_zero_reviews(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query_summary": {
                "total_positive": 0,
                "total_negative": 0,
                "total_reviews": 0,
                "review_score": None,
            }
        }
        enricher = SteamScoreEnricher()
        with patch("requests.get", return_value=mock_response):
            # Sin reseñas no hay nada que aportar: None significa "no aplicar".
            assert enricher._fetch_score("12345") is None

    def test_fetch_score_network_error(self):
        enricher = SteamScoreEnricher()
        with patch("requests.get", side_effect=ConnectionError("no network")):
            assert enricher._fetch_score("12345") is None

    def test_network_error_preserves_existing_scores(self, make_game):
        # Un fallo de red no debe borrar valoraciones ya conocidas.
        g = make_game(steamdb_score=88.0, steam_review=8, review_pos=900, review_neg=100)
        g.set_store(Stores.STEAM, "440")
        enricher = SteamScoreEnricher(overwrite=True)
        with patch("requests.get", side_effect=ConnectionError("no network")):
            result = enricher.enrich(g)
        assert result.steamdb_score == 88.0
        assert result.steam_review == 8
        assert result.review_pos == 900

    def test_bayesian_formula(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query_summary": {
                "total_positive": 990,
                "total_negative": 10,
                "total_reviews": 1000,
                "review_score": 9,
            }
        }
        enricher = SteamScoreEnricher()
        with patch("requests.get", return_value=mock_response):
            steamdb, review, pos, neg = enricher._fetch_score("12345")
            assert steamdb is not None
            # 99% positive with 1000 reviews → Bayesian should be very high
            assert steamdb > 90.0

    def test_does_not_mutate_original(self, make_game):
        g = make_game(steamdb_score=None, steam_review=None,
                      stores={"steam": "12345"})
        with patch.object(SteamScoreEnricher, "_fetch_score") as mock_fetch:
            mock_fetch.return_value = (80.0, 7, 500, 50)
            enricher = SteamScoreEnricher()
            result = enricher.enrich(g)
            assert result is not g
            assert g.steamdb_score is None
            assert result.steamdb_score == 80.0
