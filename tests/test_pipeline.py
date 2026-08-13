from unittest.mock import Mock

import pytest

from puntueitor.core.pipeline.scoring_ops import score_library, score_game
from puntueitor.core.pipeline.filter_library import filter_library, or_filter_library, and_filter_library
from puntueitor.core.pipeline.enrichment_pipeline import EnrichmentPipeline
from puntueitor.core.models import Game, Library, ScoredGame, ScoringContext
from puntueitor.core.protocols import GameScorer


class DummyScorer(GameScorer):
    def score(self, game, ctx):
        return game.critic_score / 100 if game.critic_score else 0.0


class TestScoreGame:
    def test_score_game_returns_scored_game(self, sample_game):
        scorer = DummyScorer()
        ctx = ScoringContext()
        result = score_game(sample_game, scorer, ctx)
        assert isinstance(result, ScoredGame)
        assert result.game is sample_game
        assert result.score == 0.80


class TestScoreLibrary:
    def test_score_empty_library(self, empty_library):
        scorer = DummyScorer()
        ctx = ScoringContext()
        result = score_library(empty_library, scorer, ctx)
        assert len(result) == 0

    def test_score_library_returns_sorted(self, sample_library):
        scorer = DummyScorer()
        ctx = ScoringContext()
        result = score_library(sample_library, scorer, ctx)
        scores = [sg.score for sg in result]
        assert scores == sorted(scores, reverse=True)

    def test_duration_zero_delegates_to_scorer(self, make_game):
        # duration_hours=0.0 is HLTBEnricher's "unknown" sentinel, not a real
        # zero-length game, so it must not be special-cased to score 0.0.
        g = make_game(duration_hours=0.0, critic_score=100.0)
        lib = Library.from_iterable([g])
        scorer = DummyScorer()
        ctx = ScoringContext()
        result = score_library(lib, scorer, ctx)
        assert result.scored_games[0].score == 1.0

    def test_duration_none_gets_normal_score(self, make_game):
        g = make_game(duration_hours=None, critic_score=80.0)
        lib = Library.from_iterable([g])
        scorer = DummyScorer()
        ctx = ScoringContext()
        result = score_library(lib, scorer, ctx)
        assert result.scored_games[0].score == 0.80

    def test_only_duration_zero_delegates_to_scorer(self, sample_games):
        g1 = sample_games[0]
        g2 = sample_games[4]
        g2_copy = Game(igdb_id=g2.igdb_id, title=g2.title,
                        critic_score=100.0, duration_hours=0.0)
        lib = Library.from_iterable([g1, g2_copy])
        scorer = DummyScorer()
        ctx = ScoringContext()
        result = score_library(lib, scorer, ctx)
        scored = {sg.game.igdb_id: sg.score for sg in result}
        assert scored[1] == 0.97  # g1 critic 97/100
        assert scored[5] == 1.0   # g2 duration 0 (unknown), critic 100/100


class TestFilterLibrary:
    def test_filter_library(self, sample_library):
        from puntueitor.core.filters import FinishedFilter
        f = FinishedFilter(finished=True)
        result = filter_library(sample_library, f)
        assert len(result) == 2
        assert all(g.finished for g in result)

    def test_filter_library_no_matches(self, empty_library):
        from puntueitor.core.filters import FinishedFilter
        f = FinishedFilter(finished=True)
        result = filter_library(empty_library, f)
        assert len(result) == 0

    def test_or_filter_library(self, sample_library):
        from puntueitor.core.filters import FinishedFilter, FavoriteFilter
        result = or_filter_library(sample_library, [
            FinishedFilter(finished=True),
            FavoriteFilter(favorite=True),
        ])
        assert len(result) >= 1
        for g in result:
            assert g.finished or g.favorite

    def test_and_filter_library(self, sample_library):
        from puntueitor.core.filters import FinishedFilter, HiddenFilter
        result = and_filter_library(sample_library, [
            FinishedFilter(finished=True),
            HiddenFilter(hidden=True),
        ])
        assert len(result) == 1
        assert result.games[0].igdb_id == 3


class TestEnrichmentPipeline:
    def test_enrich_applies_all_enrichers(self, sample_library):
        mock1 = Mock()
        mock1.enrich.side_effect = lambda g: g
        mock2 = Mock()
        mock2.enrich.side_effect = lambda g: g
        pipeline = EnrichmentPipeline([mock1, mock2])
        pipeline.enrich(sample_library)
        assert mock1.enrich.call_count == len(sample_library)
        assert mock2.enrich.call_count == len(sample_library)

    def test_enricher_exception_continues(self, sample_library):
        broken = Mock()
        broken.enrich.side_effect = RuntimeError("fail")
        working = Mock()
        working.enrich.side_effect = lambda g: g
        pipeline = EnrichmentPipeline([broken, working])
        pipeline.enrich(sample_library)
        assert working.enrich.call_count == len(sample_library)

    def test_empty_enrichers(self, sample_library):
        pipeline = EnrichmentPipeline([])
        result = pipeline.enrich(sample_library)
        assert len(result) == len(sample_library)
