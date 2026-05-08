import os
import tempfile
import pytest
import time

from puntueitor.core.cachers.igdb_cacher import IGDBCacher


class TestIGDBCacher:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_igdb.sqlite")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_get_game(self):
        cacher = IGDBCacher(self.db_path)

        game_data = {
            "id": 12345,
            "name": "Test Game",
            "aggregated_rating": 85.5,
            "cover": {"url": "//cover/game.jpg"},
            "genres": [{"name": "Action"}],
            "rating": 90.0,
            "storyline": "A test story",
            "first_release_date": 1609459200,
            "total_rating": 87.5,
            "_schema_version": 1
        }

        cacher.save_game(game_data)

        result = cacher.get_game(12345)
        assert result is not None
        assert result["name"] == "Test Game"
        assert result["aggregated_rating"] == 85.5
        assert result["cover"]["url"] == "//cover/game.jpg"
        assert len(result["genres"]) == 1

    def test_cache_expiration(self):
        cacher = IGDBCacher(self.db_path, ttl_seconds=1)

        game_data = {
            "id": 12345,
            "name": "Test Game",
            "_schema_version": 1
        }

        cacher.save_game(game_data)

        result = cacher.get_game(12345)
        assert result is not None

        time.sleep(1.5)

        result_expired = cacher.get_game(12345)
        assert result_expired is None

    def test_get_nonexistent_game(self):
        cacher = IGDBCacher(self.db_path)

        result = cacher.get_game(99999)
        assert result is None

    def test_update_existing_game(self):
        cacher = IGDBCacher(self.db_path)

        game_data = {
            "id": 12345,
            "name": "Original Name",
            "aggregated_rating": 80.0,
            "_schema_version": 1
        }
        cacher.save_game(game_data)

        game_data["name"] = "Updated Name"
        game_data["aggregated_rating"] = 90.0
        cacher.save_game(game_data)

        result = cacher.get_game(12345)
        assert result["name"] == "Updated Name"
        assert result["aggregated_rating"] == 90.0

    def test_get_all_cached_ids(self):
        cacher = IGDBCacher(self.db_path)

        for i in range(5):
            cacher.save_game({
                "id": 1000 + i,
                "name": f"Game {i}",
                "_schema_version": 1
            })

        ids = cacher.get_all_cached_ids()
        assert len(ids) == 5
        assert 1000 in ids
        assert 1004 in ids