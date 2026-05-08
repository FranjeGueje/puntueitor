import pytest
from unittest.mock import MagicMock

from puntueitor.core.selector.steam_selector import SteamSelector
from puntueitor.core.models import Game, SelectionContext
from puntueitor.core.models.game import Stores


class TestSteamSelector:
    def test_select_returns_none_for_empty_candidates(self):
        selector = SteamSelector()
        ctx = SelectionContext()
        result = selector.select([], ctx)
        assert result is None

    def test_select_returns_single_candidate(self):
        selector = SteamSelector()
        ctx = SelectionContext()

        game = Game(
            igdb_id=1,
            title="Single Game",
            critic_score=80.0,
            user_score=85.0
        )

        result = selector.select([game], ctx)
        assert result is game

    def test_select_returns_highest_score(self):
        selector = SteamSelector()
        ctx = SelectionContext()

        games = [
            Game(igdb_id=1, title="Low Score Game", critic_score=50.0, user_score=60.0),
            Game(igdb_id=2, title="High Score Game", critic_score=90.0, user_score=95.0),
            Game(igdb_id=3, title="Medium Score Game", critic_score=70.0, user_score=75.0),
        ]

        result = selector.select(games, ctx)
        assert result.igdb_id == 2

    def test_select_prefers_more_complete_data_on_tie(self):
        selector = SteamSelector()
        ctx = SelectionContext()

        games = [
            Game(igdb_id=1, title="Incomplete Game", critic_score=80.0),
            Game(igdb_id=2, title="Complete Game", critic_score=80.0, user_score=85.0, cover_url="http://test.jpg"),
        ]

        result = selector.select(games, ctx)
        assert result.igdb_id == 2

    def test_select_handles_none_scores(self):
        selector = SteamSelector()
        ctx = SelectionContext()

        games = [
            Game(igdb_id=1, title="No Scores", critic_score=None, user_score=None),
            Game(igdb_id=2, title="Has Score", critic_score=80.0, user_score=None),
        ]

        result = selector.select(games, ctx)
        assert result.igdb_id == 2

    def test_select_handles_all_none_scores(self):
        selector = SteamSelector()
        ctx = SelectionContext()

        games = [
            Game(igdb_id=1, title="Game 1", critic_score=None, user_score=None),
            Game(igdb_id=2, title="Game 2", critic_score=None, user_score=None),
        ]

        result = selector.select(games, ctx)
        assert result is not None