import pytest

from puntueitor.core.selector.base_selector import SimpleSelector
from puntueitor.core.selector.steam_selector import SteamSelector
from puntueitor.core.models import Game, SelectionContext


class TestSimpleSelector:
    def test_select_first(self, sample_games):
        selector = SimpleSelector()
        result = selector.select(sample_games, None)
        assert result is sample_games[0]

    def test_select_empty(self):
        selector = SimpleSelector()
        result = selector.select([], None)
        assert result is None

    @pytest.mark.parametrize("candidates", [None, ()])
    def test_select_none_or_empty(self, candidates):
        selector = SimpleSelector()
        result = selector.select(candidates, None)
        assert result is None

    def test_single_candidate(self, sample_game):
        selector = SimpleSelector()
        result = selector.select([sample_game], None)
        assert result is sample_game


class TestSteamSelector:
    def test_none_candidates(self, selection_context):
        selector = SteamSelector()
        result = selector.select(None, selection_context)
        assert result is None

    def test_empty_candidates(self, selection_context):
        selector = SteamSelector()
        result = selector.select([], selection_context)
        assert result is None

    def test_single_candidate(self, sample_game, selection_context):
        selector = SteamSelector()
        result = selector.select([sample_game], selection_context)
        assert result is sample_game

    def test_picks_highest_score(self, sample_games, selection_context):
        selector = SteamSelector()
        candidates = [sample_games[0], sample_games[4]]
        result = selector.select(candidates, selection_context)
        assert result is sample_games[0]

    def test_tie_break_by_completeness(self, make_game, selection_context):
        g1 = make_game(igdb_id=1, title="Game A",
                       critic_score=0.0, user_score=0.0,
                       steamdb_score=None,
                       duration_hours=None, cover_url=None)
        g2 = make_game(igdb_id=2, title="Game B",
                       critic_score=0.0, user_score=0.0,
                       steamdb_score=None,
                       duration_hours=20.0, cover_url="http://cover")
        selector = SteamSelector()
        result = selector.select([g1, g2], selection_context)
        assert result is g2

    def test_attribute_error_on_bad_items(self, selection_context):
        selector = SteamSelector()
        with pytest.raises(AttributeError):
            selector.select([1, 2, 3], selection_context)
