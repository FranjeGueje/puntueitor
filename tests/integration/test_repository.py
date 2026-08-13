import json
import pytest
from pathlib import Path
from datetime import date

from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.models import Game, Library, Stores


class TestLibraryRepository:
    def test_empty_repo_returns_empty_library(self, tmp_path):
        repo = LibraryRepository(cache_dir=tmp_path)
        lib = repo.load()
        assert len(lib) == 0

    def test_save_game_and_load(self, tmp_path):
        repo = LibraryRepository(cache_dir=tmp_path)
        game = Game(
            igdb_id=1001,
            title="Test Game",
            critic_score=85.0,
            user_score=75.0,
            duration_hours=20.0,
            steamdb_score=80.0,
            steam_review=7,
            review_pos=500,
            review_neg=50,
        )
        game.set_store(Stores.STEAM, "12345")

        # Save the resolver mapping (as pipeline would)
        repo.resolvers_cacher.set_igdb_ids("steam", "12345", [1001])

        # Save IGDB data (as pipeline would)
        igdb_raw = {
            "id": 1001,
            "name": "Test Game",
            "aggregated_rating": 85.0,
            "rating": 75.0,
            "cover": {"url": "//images.igdb.com/t_thumb/game.jpg"},
            "storyline": "A test",
            "first_release_date": 1592179200,
            "genres": [{"name": "Action"}],
        }
        repo.igdb_cacher.save_game(igdb_raw)

        # Save extras
        repo.save_game(game)

        # Save user status
        repo.library_cacher.set_status(
            1001, finished=True, hidden=False, backlog=True, favorite=False
        )

        # Load
        lib = repo.load()
        assert len(lib) == 1
        loaded = lib.games[0]
        assert loaded.igdb_id == 1001
        assert loaded.title == "Test Game"
        assert loaded.critic_score == 85.0
        assert loaded.user_score == 75.0
        assert loaded.duration_hours == 20.0
        assert loaded.steamdb_score == 80.0
        assert loaded.finished is True
        assert loaded.backlog is True
        assert loaded.hidden is False
        assert loaded.favorite is False
        assert loaded.genres == ("Action",)

    def test_load_skips_missing_igdb_data(self, tmp_path):
        repo = LibraryRepository(cache_dir=tmp_path)
        repo.resolvers_cacher.set_igdb_ids("steam", "12345", [9999])
        lib = repo.load()
        assert len(lib) == 0

    def test_save_library(self, tmp_path):
        repo = LibraryRepository(cache_dir=tmp_path)
        game = Game(igdb_id=1, title="Game 1", duration_hours=10.0)
        game.set_store(Stores.STEAM, "111")
        repo.resolvers_cacher.set_igdb_ids("steam", "111", [1])
        igdb_raw = {"id": 1, "name": "Game 1", "genres": []}
        repo.igdb_cacher.save_game(igdb_raw)

        game2 = Game(igdb_id=2, title="Game 2", duration_hours=20.0)
        game2.set_store(Stores.EPIC, "222")
        repo.resolvers_cacher.set_igdb_ids("epic", "222", [2])
        igdb_raw2 = {"id": 2, "name": "Game 2", "genres": []}
        repo.igdb_cacher.save_game(igdb_raw2)

        lib = Library.from_iterable([game, game2])
        repo.save(lib)

        loaded = repo.load()
        assert len(loaded) == 2

    def test_statuses_loaded_correctly(self, tmp_path):
        repo = LibraryRepository(cache_dir=tmp_path)
        game = Game(igdb_id=1, title="Test")
        game.set_store(Stores.STEAM, "111")
        repo.resolvers_cacher.set_igdb_ids("steam", "111", [1])
        igdb_raw = {"id": 1, "name": "Test", "genres": []}
        repo.igdb_cacher.save_game(igdb_raw)
        repo.library_cacher.set_status(
            1, finished=True, hidden=True, backlog=True, favorite=True
        )

        lib = repo.load()
        loaded = lib.games[0]
        assert loaded.finished is True
        assert loaded.hidden is True
        assert loaded.backlog is True
        assert loaded.favorite is True
