import pytest

from puntueitor.core.models import Game
from puntueitor.core.filters import (
    NameFilter, DurationFilter, FinishedFilter,
    FavoriteFilter, BacklogFilter, HiddenFilter,
)


class TestNameFilter:
    def test_exact_match(self, make_game):
        g = make_game(title="Zelda Breath of the Wild")
        f = NameFilter("Zelda Breath of the Wild")
        assert f.matches(g) is True

    def test_partial_substring(self, make_game):
        g = make_game(title="The Legend of Zelda: Ocarina of Time")
        f = NameFilter("Zelda")
        assert f.matches(g) is True

    def test_normalized_substring(self, make_game):
        g = make_game(title="The Legend of Zelda (Remastered)")
        f = NameFilter("Zelda")
        assert f.matches(g) is True

    def test_no_match(self, make_game):
        g = make_game(title="Elden Ring")
        f = NameFilter("Mario")
        assert f.matches(g) is False

    def test_fuzzy_match_high_threshold(self, make_game):
        g = make_game(title="The Legend of Zelda")
        f = NameFilter("Zelda", similarity_thrd=0.3)
        assert f.matches(g) is True

    def test_fuzzy_match_low_similarity(self, make_game):
        g = make_game(title="Elden Ring")
        f = NameFilter("Zelda", similarity_thrd=0.9)
        assert f.matches(g) is False

    def test_empty_query(self, make_game):
        g = make_game(title="Any Game")
        f = NameFilter("")
        assert f.matches(g) is True

    def test_case_insensitive(self, make_game):
        g = make_game(title="The Legend of Zelda")
        f = NameFilter("zelda")
        assert f.matches(g) is True


class TestDurationFilter:
    def test_under_limit(self, make_game):
        g = make_game(duration_hours=15.0)
        f = DurationFilter(20.0)
        assert f.matches(g) is True

    def test_over_limit(self, make_game):
        g = make_game(duration_hours=25.0)
        f = DurationFilter(20.0)
        assert f.matches(g) is False

    def test_exact_limit(self, make_game):
        g = make_game(duration_hours=20.0)
        f = DurationFilter(20.0)
        assert f.matches(g) is True

    def test_none_duration_passes(self, make_game):
        g = make_game(duration_hours=None)
        f = DurationFilter(20.0)
        assert f.matches(g) is True

    def test_zero_limit(self, make_game):
        g1 = make_game(duration_hours=0.0)
        g2 = make_game(duration_hours=10.0)
        f = DurationFilter(0.0)
        assert f.matches(g1) is True
        assert f.matches(g2) is False


class TestFinishedFilter:
    def test_finished_true(self, make_game):
        g = make_game(finished=True)
        f = FinishedFilter(True)
        assert f.matches(g) is True

    def test_finished_false(self, make_game):
        g = make_game(finished=False)
        f = FinishedFilter(False)
        assert f.matches(g) is True

    def test_mismatch(self, make_game):
        g = make_game(finished=True)
        f = FinishedFilter(False)
        assert f.matches(g) is False


class TestFavoriteFilter:
    def test_favorite_true(self, make_game):
        g = make_game(favorite=True)
        f = FavoriteFilter(True)
        assert f.matches(g) is True

    def test_not_favorite(self, make_game):
        g = make_game(favorite=False)
        f = FavoriteFilter(True)
        assert f.matches(g) is False


class TestBacklogFilter:
    def test_backlog_true(self, make_game):
        g = make_game(backlog=True)
        f = BacklogFilter(True)
        assert f.matches(g) is True

    def test_not_backlog(self, make_game):
        g = make_game(backlog=False)
        f = BacklogFilter(True)
        assert f.matches(g) is False


class TestHiddenFilter:
    def test_hidden_true(self, make_game):
        g = make_game(hidden=True)
        f = HiddenFilter(True)
        assert f.matches(g) is True

    def test_not_hidden(self, make_game):
        g = make_game(hidden=False)
        f = HiddenFilter(True)
        assert f.matches(g) is False
