import pytest
from math import exp, isclose

from puntueitor.core.models import Game
from puntueitor.core.scoring.helpers import score_or_steam
from puntueitor.core.scoring.atomic import (
    BasicScoreScorer, CriticScoreScorer, UserScoreScorer,
    DurationScoreScorer, GenreScorer,
)
from puntueitor.core.scoring.mixed_score import MixedScore
from puntueitor.core.scoring.weighted_score import WeightedScore
from puntueitor.core.scoring.available_time import AvailableTimeScorer


class TestScoreOrSteam:
    def test_value_present(self):
        assert score_or_steam(80, None) == 0.8

    def test_value_zero_steam_present(self):
        assert score_or_steam(0, 75) == 0.75

    def test_both_zero(self):
        assert score_or_steam(0, 0) == 0.0

    def test_both_none(self):
        assert score_or_steam(0, 0) == 0.0

    def test_value_negative(self):
        assert score_or_steam(-10, 50) == 0.5

    def test_steamdb_score_division(self):
        assert score_or_steam(0, 100) == 1.0


class TestCriticScoreScorer:
    def test_with_critic_score(self, sample_game, scoring_context):
        scorer = CriticScoreScorer()
        score = scorer.score(sample_game, scoring_context)
        assert score == 0.80

    def test_without_critic_with_steamdb(self, make_game, scoring_context):
        g = make_game(critic_score=0, steamdb_score=50.0)
        scorer = CriticScoreScorer()
        score = scorer.score(g, scoring_context)
        assert score == 0.50

    def test_no_scores(self, scoring_context):
        g = Game(igdb_id=1, title="No Score")
        scorer = CriticScoreScorer()
        score = scorer.score(g, scoring_context)
        assert score == 0.0


class TestUserScoreScorer:
    def test_with_user_score(self, sample_game, scoring_context):
        scorer = UserScoreScorer()
        score = scorer.score(sample_game, scoring_context)
        assert score == 0.75

    def test_fallback_to_steamdb(self, make_game, scoring_context):
        g = make_game(user_score=0, steamdb_score=80.0)
        scorer = UserScoreScorer()
        score = scorer.score(g, scoring_context)
        assert score == 0.80


class TestBasicScoreScorer:
    def test_average_of_both(self, sample_game, scoring_context):
        scorer = BasicScoreScorer()
        score = scorer.score(sample_game, scoring_context)
        expected = (0.80 + 0.75) / 2.0
        assert score == expected

    def test_fallback_to_steamdb(self, make_game, scoring_context):
        g = make_game(critic_score=0, user_score=0, steamdb_score=60.0)
        scorer = BasicScoreScorer()
        score = scorer.score(g, scoring_context)
        assert score == 0.60

    def test_all_none(self, make_game, scoring_context):
        g = make_game(critic_score=None, user_score=None, steamdb_score=None)
        scorer = BasicScoreScorer()
        score = scorer.score(g, scoring_context)
        assert score == 0.0


class TestDurationScoreScorer:
    def test_ideal_duration_returns_one(self, scoring_context):
        scorer = DurationScoreScorer()
        g = Game(igdb_id=1, title="T", duration_hours=15.0)
        assert scorer.score(g, scoring_context) == 1.0

    def test_max_duration_returns_zero(self, scoring_context):
        scorer = DurationScoreScorer()
        g = Game(igdb_id=1, title="T", duration_hours=60.0)
        assert scorer.score(g, scoring_context) == 0.0

    def test_below_ideal_returns_one(self, scoring_context):
        scorer = DurationScoreScorer()
        g = Game(igdb_id=1, title="T", duration_hours=10.0)
        assert scorer.score(g, scoring_context) == 1.0

    def test_linear_fall(self, scoring_context):
        scorer = DurationScoreScorer()
        g = Game(igdb_id=1, title="T", duration_hours=37.5)
        expected = 1.0 - (37.5 - 15.0) / (60.0 - 15.0)
        assert scorer.score(g, scoring_context) == expected

    def test_none_duration(self, scoring_context):
        scorer = DurationScoreScorer()
        g = Game(igdb_id=1, title="T", duration_hours=None)
        assert scorer.score(g, scoring_context) == 0.0

    def test_zero_duration(self, scoring_context):
        scorer = DurationScoreScorer()
        g = Game(igdb_id=1, title="T", duration_hours=0.0)
        assert scorer.score(g, scoring_context) == 1.0


class TestAvailableTimeScorer:
    def test_within_time(self, scoring_context):
        scorer = AvailableTimeScorer()
        g = Game(igdb_id=1, title="T", duration_hours=10.0)
        score = scorer.score(g, scoring_context)
        assert 0.5 <= score <= 1.0

    def test_exceeds_time(self, scoring_context):
        scorer = AvailableTimeScorer()
        g = Game(igdb_id=1, title="T", duration_hours=40.0)
        score = scorer.score(g, scoring_context)
        assert -1.0 <= score < 0.0

    def test_no_available_hours(self, make_game, scoring_context):
        ctx = scoring_context
        ctx.__dict__["available_hours"] = None
        scorer = AvailableTimeScorer()
        score = scorer.score(make_game(duration_hours=10.0), ctx)
        assert score == 0.0

    def test_no_duration(self, make_game, scoring_context):
        scorer = AvailableTimeScorer()
        score = scorer.score(make_game(duration_hours=None), scoring_context)
        assert score == 0.0

    def test_zero_duration_gives_highest(self, scoring_context):
        scorer = AvailableTimeScorer()
        g = Game(igdb_id=1, title="T", duration_hours=0.0)
        assert scorer.score(g, scoring_context) == 1.0


class TestMixedScore:
    def test_default_weights(self, sample_game, scoring_context):
        scorer = MixedScore()
        score = scorer.score(sample_game, scoring_context)
        critic = score_or_steam(sample_game.critic_score, sample_game.steamdb_score)
        user = score_or_steam(sample_game.user_score, sample_game.steamdb_score)
        duration = exp(-sample_game.duration_hours / 80.0)
        expected = 0.3 * critic + 0.5 * user + 0.2 * duration
        assert isclose(score, expected, rel_tol=1e-6)

    def test_custom_weights(self, sample_game, scoring_context):
        scorer = MixedScore(weight_critics=0.5, weight_users=0.3, weight_duration=0.2)
        score = scorer.score(sample_game, scoring_context)
        assert score > 0

    def test_assertion_on_bad_weights(self):
        with pytest.raises(AssertionError):
            MixedScore(weight_critics=2.0, weight_users=0.0, weight_duration=0.0)

    def test_none_duration(self, make_game, scoring_context):
        g = make_game(duration_hours=None)
        scorer = MixedScore()
        score = scorer.score(g, scoring_context)
        critic = score_or_steam(g.critic_score, g.steamdb_score)
        user = score_or_steam(g.user_score, g.steamdb_score)
        expected = 0.3 * critic + 0.5 * user + 0.2 * 0.5
        assert isclose(score, expected, rel_tol=1e-6)

    def test_steamdb_fallback(self, make_game, scoring_context):
        g = make_game(critic_score=0, user_score=0, steamdb_score=50.0)
        scorer = MixedScore()
        score = scorer.score(g, scoring_context)
        assert score > 0


class TestWeightedScore:
    def test_single_scorer(self, sample_game, scoring_context):
        scorers = [(CriticScoreScorer(), 1.0)]
        scorer = WeightedScore(scorers)
        score = scorer.score(sample_game, scoring_context)
        expected = CriticScoreScorer().score(sample_game, scoring_context)
        assert score == expected

    def test_multiple_scorers(self, sample_game, scoring_context):
        scorers = [
            (CriticScoreScorer(), 0.5),
            (UserScoreScorer(), 0.5),
        ]
        scorer = WeightedScore(scorers)
        score = scorer.score(sample_game, scoring_context)
        expected = 0.5 * CriticScoreScorer().score(sample_game, scoring_context) \
                 + 0.5 * UserScoreScorer().score(sample_game, scoring_context)
        assert isclose(score, expected, rel_tol=1e-6)

    def test_scorer_exception_caught(self, sample_game, scoring_context):
        class BrokenScorer:
            def score(self, game, ctx):
                raise TypeError("broken")
        scorers = [(BrokenScorer(), 1.0)]
        scorer = WeightedScore(scorers)
        score = scorer.score(sample_game, scoring_context)
        assert score == 0.0

    def test_partial_failure(self, sample_game, scoring_context):
        class BrokenScorer:
            def score(self, game, ctx):
                raise ValueError("broken")
        scorers = [
            (CriticScoreScorer(), 1.0),
            (BrokenScorer(), 1.0),
        ]
        scorer = WeightedScore(scorers)
        score = scorer.score(sample_game, scoring_context)
        expected = CriticScoreScorer().score(sample_game, scoring_context)
        assert isclose(score, expected, rel_tol=1e-6)

    def test_empty_scorers(self, scoring_context):
        scorer = WeightedScore([])
        g = Game(igdb_id=1, title="T")
        assert scorer.score(g, scoring_context) == 0.0


class TestGenreScorer:
    def test_preferred_genre_boost(self, scoring_context):
        g = Game(igdb_id=1, title="T", genres=("Action",))
        scorer = GenreScorer()
        assert scorer.score(g, scoring_context) == 1.0

    def test_disliked_genre_penalty(self, scoring_context):
        g = Game(igdb_id=1, title="T", genres=("Horror",))
        scorer = GenreScorer()
        assert scorer.score(g, scoring_context) == -1.0

    def test_mixed_genres(self, scoring_context):
        g = Game(igdb_id=1, title="T", genres=("Action", "Horror"))
        scorer = GenreScorer()
        score = scorer.score(g, scoring_context)
        assert -1.0 < score < 1.0

    def test_no_genres(self, scoring_context):
        g = Game(igdb_id=1, title="T", genres=())
        scorer = GenreScorer()
        assert scorer.score(g, scoring_context) == 0.0

    def test_no_preferences(self, scoring_context):
        ctx = scoring_context
        ctx.__dict__["preferred_genres"] = None
        ctx.__dict__["disliked_genres"] = None
        g = Game(igdb_id=1, title="T", genres=("Action",))
        scorer = GenreScorer()
        assert scorer.score(g, scoring_context) == 0.0
