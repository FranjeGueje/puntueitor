import pytest
from dataclasses import FrozenInstanceError
from datetime import date

from puntueitor.core.models import Game, Library, Stores, ScoredGame, ScoredLibrary, ScoringContext
from puntueitor.core.models.util import normalize_title, similarity


class TestNormalizeTitle:
    def test_basic_lowercase(self):
        assert normalize_title("The Legend of Zelda") == "the legend of zelda"

    def test_removes_parentheses(self):
        assert normalize_title("Zelda (Remastered)") == "zelda"

    def test_removes_brackets(self):
        assert normalize_title("Game [GOTY]") == "game"

    def test_removes_colon_and_dash(self):
        result = normalize_title("Metroid: Dread – Special")
        assert ":" not in result and "–" not in result

    def test_removes_edition_words(self):
        result = normalize_title("Game of the Thrones Definitive Edition Remastered")
        assert "edition" not in result
        assert "remastered" not in result
        assert "definitive" not in result

    def test_removes_bundle_pack_collection(self):
        assert normalize_title("Humble Bundle Pack Collection") == "humble"

    def test_empty_string(self):
        assert normalize_title("") == ""

    def test_only_stop_words(self):
        assert normalize_title("Remastered Edition Collection") == ""


class TestSimilarity:
    def test_identical_strings(self):
        assert similarity("hello", "hello") == 1.0

    def test_completely_different(self):
        assert similarity("abc", "xyz") < 0.2

    def test_partial_match(self):
        s = similarity("zelda", "the legend of zelda")
        assert 0.3 < s < 1.0


class TestGameCreation:
    def test_default_values(self, make_game):
        g = make_game()
        assert g.igdb_id == 1
        assert g.title == "Test Game"
        assert g.finished is False
        assert g.hidden is False
        assert g.backlog is False
        assert g.favorite is False
        assert g.stores == {}

    def test_slots_enabled(self):
        g = Game(igdb_id=1, title="Test")
        with pytest.raises(AttributeError):
            g.nonexistent_attr = 42

    def test_normalized_title_computed(self, make_game):
        g = make_game(title="The Legend of Zelda (Remastered)")
        assert "remastered" not in g.title_normalized
        assert "zelda" in g.title_normalized


class TestSetStore:
    def test_set_store_success(self, make_game):
        g = make_game()
        g.set_store(Stores.STEAM, "12345")
        assert g.stores[Stores.STEAM] == "12345"

    def test_set_store_empty_raises(self, make_game):
        g = make_game()
        with pytest.raises(ValueError, match="cannot be empty"):
            g.set_store(Stores.STEAM, "")

    def test_multiple_stores(self, make_game):
        g = make_game()
        g.set_store(Stores.STEAM, "12345")
        g.set_store(Stores.EPIC, "abc-def")
        assert len(g.stores) == 2


class TestGameSerialization:
    def test_to_dict_round_trip(self, make_game):
        g1 = make_game(
            igdb_id=42,
            title="Test Round",
            release_date=date(2021, 1, 1),
            stores={Stores.STEAM: "999"},
        )
        data = g1.to_dict()
        g2 = Game.from_dict(data)

        assert g2.igdb_id == g1.igdb_id
        assert g2.title == g1.title
        assert g2.genres == g1.genres
        assert g2.release_date == g1.release_date
        assert g2.critic_score == g1.critic_score
        assert g2.user_score == g1.user_score
        assert g2.duration_hours == g1.duration_hours
        assert g2.steamdb_score == g1.steamdb_score
        assert g2.stores[Stores.STEAM] == "999"
        assert g2.finished == g1.finished
        assert g2.hidden == g1.hidden

    def test_from_dict_invalid_stores_ignored(self):
        data = {
            "igdb_id": 1,
            "title": "Test",
            "stores": {"steam": "123", "invalid_store": "abc"},
        }
        g = Game.from_dict(data)
        assert Stores.STEAM in g.stores
        assert len(g.stores) == 1

    def test_from_dict_no_release_date(self):
        data = {"igdb_id": 1, "title": "Test"}
        g = Game.from_dict(data)
        assert g.release_date is None

    def test_from_dict_default_flags(self):
        data = {"igdb_id": 1, "title": "Test"}
        g = Game.from_dict(data)
        assert g.finished is False
        assert g.hidden is False

    def test_to_dict_contains_all_keys(self, make_game):
        g = make_game()
        data = g.to_dict()
        expected_keys = {
            "igdb_id", "title", "genres", "storyline", "release_date",
            "cover_url", "critic_score", "user_score", "duration_hours",
            "steam_review", "steamdb_score", "review_pos", "review_neg",
            "stores", "finished", "hidden", "backlog", "favorite",
        }
        assert set(data.keys()) == expected_keys


class TestLibrary:
    def test_empty_library(self, empty_library):
        assert len(empty_library) == 0
        assert list(empty_library) == []

    def test_from_iterable(self, sample_games):
        lib = Library.from_iterable(sample_games)
        assert len(lib) == 5

    def test_contains_igdb_id(self, sample_library):
        assert sample_library.contains_igdb_id(1) is True
        assert sample_library.contains_igdb_id(999) is False

    def test_iteration(self, sample_library):
        ids = [g.igdb_id for g in sample_library]
        assert ids == [1, 2, 3, 4, 5]

    def test_from_iterable_with_tuple(self):
        lib = Library.from_iterable((Game(igdb_id=1, title="A"), Game(igdb_id=2, title="B")))
        assert len(lib) == 2

    def test_empty_from_iterable(self):
        lib = Library.from_iterable([])
        assert len(lib) == 0


class TestScoredGame:
    def test_frozen(self):
        sg = ScoredGame(game=Game(igdb_id=1, title="T"), score=0.5)
        with pytest.raises(FrozenInstanceError):
            sg.score = 0.8

    def test_attributes(self, sample_game):
        sg = ScoredGame(game=sample_game, score=0.85)
        assert sg.game.igdb_id == 1
        assert sg.score == 0.85


class TestScoredLibrary:
    def test_empty(self):
        sl = ScoredLibrary.from_iterable([])
        assert len(sl) == 0

    def test_sort_ascending(self, sample_games):
        scored = [ScoredGame(g, i / 10) for i, g in enumerate(sample_games)]
        sl = ScoredLibrary.from_iterable(scored)
        sorted_sl = sl.sort(ascending=True)
        scores = [sg.score for sg in sorted_sl]
        assert scores == sorted(scores)

    def test_sort_descending(self, sample_games):
        scored = [ScoredGame(g, i / 10) for i, g in enumerate(sample_games)]
        sl = ScoredLibrary.from_iterable(scored)
        sorted_sl = sl.sort(ascending=False)
        scores = [sg.score for sg in sorted_sl]
        assert scores == sorted(scores, reverse=True)

    def test_none_score_sorted_last_ascending(self, sample_game):
        games = [
            ScoredGame(sample_game, 0.5),
            ScoredGame(sample_game, None),
            ScoredGame(sample_game, 0.3),
        ]
        sl = ScoredLibrary.from_iterable(games)
        sorted_sl = sl.sort(ascending=True)
        scores = [sg.score for sg in sorted_sl]
        # None stays None in the score field; sort key uses inf
        assert scores[0] == 0.3
        assert scores[1] == 0.5
        assert scores[2] is None


class TestScoringContext:
    def test_default_values(self):
        ctx = ScoringContext()
        assert ctx.available_hours is None
        assert ctx.preferred_genres is None
        assert ctx.duration_scale == 80.0
        assert ctx.neutral_duration_score == 0.5
        assert ctx.ideal_duration == 15.0
        assert ctx.max_duration == 60.0

    def test_frozen(self):
        ctx = ScoringContext()
        with pytest.raises(FrozenInstanceError):
            ctx.available_hours = 10
