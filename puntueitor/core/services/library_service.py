import logging
from collections.abc import Callable

from puntueitor.core.models import Game, Library, ScoringContext
from puntueitor.core.protocols import GameScorer, GameSorter
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.filters import NameFilter, DurationFilter, FinishedFilter, FavoriteFilter, BacklogFilter
from puntueitor.core.scoring import MixedScore
from puntueitor.core.scoring.atomic import (
    GenreScorer,
    CriticScoreScorer,
    UserScoreScorer,
    DurationScoreScorer,
)
from puntueitor.core.scoring.weighted_score import WeightedScore
from puntueitor.core.pipeline.scoring_ops import score_library
from puntueitor.core.config import ConfigManager


logger = logging.getLogger(__name__)


class LibraryService:
    def __init__(self, repo: LibraryRepository):
        self.repo = repo

    def load(self) -> Library:
        return self.repo.load()

    def save(self, library: Library) -> None:
        self.repo.save(library)

    def filter_by_name(self, library: Library, query: str) -> Library:
        f = NameFilter(query)
        filtered = [g for g in library.games if f.matches(g)]
        return Library.from_iterable(filtered)

    def filter_by_duration(self, library: Library, max_hours: float) -> Library:
        f = DurationFilter(max_hours)
        filtered = [g for g in library.games if f.matches(g)]
        return Library.from_iterable(filtered)

    def filter_by_finished(self, library: Library, finished: bool) -> Library:
        f = FinishedFilter(finished)
        filtered = [g for g in library.games if f.matches(g)]
        return Library.from_iterable(filtered)

    def filter_by_favorite(self, library: Library, favorite: bool) -> Library:
        f = FavoriteFilter(favorite)
        filtered = [g for g in library.games if f.matches(g)]
        return Library.from_iterable(filtered)

    def filter_by_backlog(self, library: Library, backlog: bool) -> Library:
        f = BacklogFilter(backlog)
        filtered = [g for g in library.games if f.matches(g)]
        return Library.from_iterable(filtered)

    def clear_filters(self, full_library: Library) -> Library:
        return full_library

    def sort(
        self,
        library: Library,
        criteria: str,
        reverse: bool = False,
    ) -> Library:
        games = list(library.games)

        if criteria == "title":
            games.sort(key=lambda g: g.title.lower(), reverse=reverse)
        elif criteria == "user_score":
            games.sort(key=lambda g: g.user_score or 0.0, reverse=reverse)
        elif criteria == "critic_score":
            games.sort(key=lambda g: g.critic_score or 0.0, reverse=reverse)
        elif criteria == "duration":
            none_val = 9999.0 if not reverse else -1.0
            games.sort(
                key=lambda g: g.duration_hours
                if g.duration_hours is not None
                else none_val,
                reverse=reverse,
            )
        elif criteria == "mixed":
            strategy = MixedScore()
            ctx = ScoringContext()
            games.sort(key=lambda g: strategy.score(g, ctx), reverse=reverse)

        return Library.from_iterable(games)

    def score(
        self,
        library: Library,
        scoring_type: str,
        ctx: ScoringContext | None = None,
    ) -> tuple[Library, dict[int, float]]:
        config = ConfigManager().get

        if ctx is None:
            ctx = ScoringContext(
                available_hours=config.scoring_available_hours,
                preferred_genres=set(config.scoring_preferred_genres) if config.scoring_preferred_genres else None,
            )

        scorer = self._get_scorer(scoring_type, config)
        if scorer is None:
            return library, {}

        scored_lib = score_library(library, scorer, ctx)
        scores_map = {sg.game.igdb_id: sg.score for sg in scored_lib.scored_games}

        sorted_games = [sg.game for sg in scored_lib.scored_games]
        return Library.from_iterable(sorted_games), scores_map

    def _get_scorer(self, scoring_type: str, config) -> GameScorer | None:
        if scoring_type == "mixed":
            return MixedScore(
                weight_critics=config.scoring_mixed_critics,
                weight_users=config.scoring_mixed_users,
                weight_duration=config.scoring_mixed_duration,
            )
        elif scoring_type == "weighted":
            return WeightedScore(
                [
                    (CriticScoreScorer(), config.scoring_weighted_critics),
                    (UserScoreScorer(), config.scoring_weighted_users),
                    (DurationScoreScorer(), config.scoring_weighted_duration),
                ]
            )
        elif scoring_type == "time":
            return self._get_available_time_scorer()
        elif scoring_type == "genre":
            return GenreScorer()
        return None

    def _get_available_time_scorer(self) -> GameScorer:
        from puntueitor.core.scoring.available_time import AvailableTimeScorer

        return AvailableTimeScorer()