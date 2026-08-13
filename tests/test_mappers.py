import pytest
from datetime import date

from puntueitor.core.mappers.igdb_mapper import IGMapperGame
from puntueitor.core.models.game import Game


RAW_FULL = {
    "id": 1234,
    "name": "Test Game",
    "genres": [{"name": "Action"}, {"name": "Adventure"}],
    "aggregated_rating": 85.0,
    "rating": 78.5,
    "cover": {"url": "//images.igdb.com/t_thumb/game.jpg"},
    "storyline": "A thrilling adventure",
    "first_release_date": 1592179200,
}


class TestMapToGame:
    def test_full_raw(self):
        game = IGMapperGame.map_to_game(RAW_FULL)
        assert game.igdb_id == 1234
        assert game.title == "Test Game"
        assert game.genres == ("Action", "Adventure")
        assert game.critic_score == 85.0
        assert game.user_score == 78.5
        assert game.cover_url == "https://images.igdb.com/t_cover_big/game.jpg"
        assert game.storyline == "A thrilling adventure"
        assert game.release_date == date(2020, 6, 15)
        assert game.duration_hours is None
        assert game.stores == {}

    def test_no_genres(self):
        raw = {**RAW_FULL, "genres": None}
        game = IGMapperGame.map_to_game(raw)
        assert game.genres == ()

    def test_empty_genres(self):
        raw = {**RAW_FULL, "genres": []}
        game = IGMapperGame.map_to_game(raw)
        assert game.genres == ()

    def test_malformed_genres(self):
        raw = {**RAW_FULL, "genres": ["not a dict"]}
        game = IGMapperGame.map_to_game(raw)
        assert game.genres == ()

    def test_no_cover(self):
        raw = {**RAW_FULL, "cover": None}
        game = IGMapperGame.map_to_game(raw)
        assert game.cover_url is None

    def test_no_storyline(self):
        raw = {**RAW_FULL, "storyline": None}
        game = IGMapperGame.map_to_game(raw)
        assert game.storyline is None

    def test_no_release_date(self):
        raw = {**RAW_FULL, "first_release_date": None}
        game = IGMapperGame.map_to_game(raw)
        assert game.release_date is None

    def test_none_release_date(self):
        raw = {**RAW_FULL, "first_release_date": None}
        game = IGMapperGame.map_to_game(raw)
        assert game.release_date is None

    def test_missing_release_date(self):
        raw = {k: v for k, v in RAW_FULL.items() if k != "first_release_date"}
        game = IGMapperGame.map_to_game(raw)
        assert game.release_date is None

    def test_no_scores(self):
        raw = {**RAW_FULL, "aggregated_rating": None, "rating": None}
        game = IGMapperGame.map_to_game(raw)
        assert game.critic_score is None
        assert game.user_score is None

    def test_duration_is_always_none(self):
        game = IGMapperGame.map_to_game(RAW_FULL)
        assert game.duration_hours is None


class TestMapToList:
    def test_single_item(self):
        games = IGMapperGame.map_to_list([RAW_FULL])
        assert len(games) == 1
        assert games[0].igdb_id == 1234

    def test_empty_list(self):
        games = IGMapperGame.map_to_list([])
        assert games == []

    def test_multiple_items(self):
        raws = [
            {**RAW_FULL, "id": 1, "name": "Game 1"},
            {**RAW_FULL, "id": 2, "name": "Game 2"},
        ]
        games = IGMapperGame.map_to_list(raws)
        assert len(games) == 2
        assert games[0].title == "Game 1"
        assert games[1].title == "Game 2"
