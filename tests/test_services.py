from unittest.mock import Mock, MagicMock, patch

import pytest

from puntueitor.core.services.library_service import LibraryService
from puntueitor.core.models import Game, Library, Stores


def make_service() -> tuple[LibraryService, Mock]:
    repo = Mock()
    service = LibraryService(repo)
    return service, repo


class TestLibraryService:
    def test_filter_by_name(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.filter_by_name(sample_library, "Zelda")
        assert len(result) == 1
        assert result.games[0].title == "Zelda Breath of the Wild"

    def test_filter_by_name_no_match(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.filter_by_name(sample_library, "NonExistent")
        assert len(result) == 0

    def test_filter_by_name_case_insensitive(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.filter_by_name(sample_library, "zelda")
        assert len(result) == 1

    def test_filter_by_duration(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.filter_by_duration(sample_library, 10.0)
        assert all(g.duration_hours is None or g.duration_hours <= 10.0
                   for g in result)

    def test_filter_by_finished_true(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.filter_by_finished(sample_library, True)
        assert all(g.finished for g in result)
        assert len(result) == 2

    def test_filter_by_finished_false(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.filter_by_finished(sample_library, False)
        assert all(not g.finished for g in result)
        assert len(result) == 3

    def test_filter_by_hidden(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.filter_by_hidden(sample_library, True)
        assert all(g.hidden for g in result)
        assert len(result) == 1

    def test_filter_by_favorite(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.filter_by_favorite(sample_library, True)
        assert all(g.favorite for g in result)

    def test_filter_by_backlog(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.filter_by_backlog(sample_library, True)
        assert all(g.backlog for g in result)

    def test_clear_filters_returns_same(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.clear_filters(sample_library)
        assert result is sample_library

    def test_filter_does_not_mutate_original(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        original_count = len(sample_library)
        service.filter_by_finished(sample_library, True)
        assert len(sample_library) == original_count
        service.filter_by_name(sample_library, "Zelda")
        assert len(sample_library) == original_count

    def test_sort_by_title(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.sort(sample_library, "title", reverse=False)
        titles = [g.title for g in result]
        assert titles == sorted(titles, key=str.lower)

    def test_sort_by_title_descending(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.sort(sample_library, "title", reverse=True)
        titles = [g.title for g in result]
        assert titles == sorted(titles, key=str.lower, reverse=True)

    def test_sort_by_critic_score(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.sort(sample_library, "critic_score", reverse=True)
        scores = [g.critic_score or 0.0 for g in result]
        assert scores == sorted(scores, reverse=True)

    def test_sort_by_duration_none_last(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        result = service.sort(sample_library, "duration", reverse=False)
        last = result.games[-1]
        assert last.duration_hours is None

    def test_score_unknown_type_returns_original(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        lib, scores = service.score(sample_library, "nonexistent")
        assert len(lib) == len(sample_library)
        assert scores == {}

    def test_score_returns_sorted_library(self, sample_library):
        repo = Mock()
        service = LibraryService(repo)
        lib, scores = service.score(sample_library, "mixed")
        assert len(scores) == len(sample_library)
        assert len(lib) == len(sample_library)

    def test_save_delegates(self):
        service, repo = make_service()
        lib = Library.from_iterable([])
        service.save(lib)
        repo.save.assert_called_once_with(lib)

    def test_load_delegates(self):
        service, repo = make_service()
        repo.load.return_value = Library.from_iterable([])
        result = service.load()
        assert len(result) == 0
        repo.load.assert_called_once()
