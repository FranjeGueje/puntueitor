import json
import pytest
from pathlib import Path

from puntueitor.core.cachers.igdb_cacher import IGDBCacher
from puntueitor.core.cachers.extras_cacher import ExtrasCacher
from puntueitor.core.cachers.resolvers_cacher import ResolversCacher
from puntueitor.core.cachers.library_cacher import LibraryCacher
from puntueitor.core.cachers.desconocidos_cacher import DesconocidosCacher


SAMPLE_GAME = {
    "id": 1234,
    "name": "Test Game",
    "aggregated_rating": 85.0,
    "rating": 78.5,
    "cover": {"url": "//images.igdb.com/t_thumb/game.jpg"},
    "storyline": "A thrilling adventure",
    "first_release_date": 1592179200,
    "genres": [{"name": "Action"}],
}


# ── IGDBCacher ──────────────────────────────────────────────────

class TestIGDBCacher:
    def test_save_and_get(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = IGDBCacher(db)
        cacher.save_game(SAMPLE_GAME)
        result = cacher.get_game(1234)
        assert result is not None
        assert result["name"] == "Test Game"
        assert result["id"] == 1234

    def test_get_nonexistent(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = IGDBCacher(db)
        result = cacher.get_game(9999)
        assert result is None

    def test_get_all_games(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = IGDBCacher(db)
        cacher.save_game(SAMPLE_GAME)
        g2 = {**SAMPLE_GAME, "id": 5678, "name": "Game 2"}
        cacher.save_game(g2)
        all_games = cacher.get_all_games()
        assert len(all_games) == 2

    def test_get_all_genres(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = IGDBCacher(db)
        cacher.save_game(SAMPLE_GAME)
        genres = cacher.get_all_genres()
        assert "Action" in genres

    def test_overwrite_existing(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = IGDBCacher(db)
        cacher.save_game(SAMPLE_GAME)
        updated = {**SAMPLE_GAME, "name": "Updated Game"}
        cacher.save_game(updated)
        result = cacher.get_game(1234)
        assert result["name"] == "Updated Game"

    def test_empty_db(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = IGDBCacher(db)
        assert cacher.get_game(1) is None
        assert cacher.get_all_games() == []
        assert cacher.get_all_genres() == []


# ── ExtrasCacher ────────────────────────────────────────────────

class TestExtrasCacher:
    def test_save_and_get(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = ExtrasCacher(db)
        cacher.save_extras(1, duration_hours=20.0, steamdb_score=80.0,
                           steam_review=7, review_pos=500, review_neg=50)
        extras = cacher.get_extras(1)
        assert extras["duration_hours"] == 20.0
        assert extras["steamdb_score"] == 80.0
        assert extras["steam_review"] == 7

    def test_get_all_extras(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = ExtrasCacher(db)
        cacher.save_extras(1, duration_hours=10.0)
        cacher.save_extras(2, duration_hours=20.0)
        all_e = cacher.get_all_extras()
        assert len(all_e) == 2
        assert all_e[1]["duration_hours"] == 10.0
        assert all_e[2]["duration_hours"] == 20.0

    def test_coalesce_partial_update(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = ExtrasCacher(db)
        cacher.save_extras(1, duration_hours=20.0, steamdb_score=80.0,
                           steam_review=7, review_pos=500, review_neg=50)
        cacher.save_extras(1, duration_hours=99.0)
        extras = cacher.get_extras(1)
        assert extras["duration_hours"] == 99.0
        assert extras["steamdb_score"] == 80.0
        assert extras["steam_review"] == 7

    def test_clear_all(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = ExtrasCacher(db)
        cacher.save_extras(1, duration_hours=10.0)
        cacher.clear_all()
        result = cacher.get_extras(1)
        assert result == {} or result is None
        assert cacher.get_all_extras() == {}

    def test_nonexistent_returns_none(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = ExtrasCacher(db)
        result = cacher.get_extras(999)
        assert result == {} or result is None


# ── ResolversCacher ─────────────────────────────────────────────

class TestResolversCacher:
    def test_set_and_get(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = ResolversCacher(db)
        cacher.set_igdb_ids("steam", "12345", [1001, 1002])
        ids = cacher.get_igdb_ids("steam", "12345")
        assert ids == [1001, 1002]

    def test_get_all_mappings(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = ResolversCacher(db)
        cacher.set_igdb_ids("steam", "12345", [1001])
        cacher.set_igdb_ids("epic", "abc", [2001])
        mappings = cacher.get_all_mappings()
        assert 1001 in mappings
        assert 2001 in mappings
        store_values = {str(k): v for k, v in mappings[1001].items()}
        assert "steam" in store_values  # stores converted to string keys

    def test_get_stores_for_igdb_id(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = ResolversCacher(db)
        cacher.set_igdb_ids("steam", "12345", [1001])
        cacher.set_igdb_ids("gog", "gog_id", [1001])
        stores = cacher.get_stores_for_igdb_id(1001)
        assert stores is not None
        store_values = {str(k): v for k, v in stores.items()}
        assert "steam" in store_values
        assert "gog" in store_values

    def test_remove_igdb_id(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = ResolversCacher(db)
        cacher.set_igdb_ids("steam", "12345", [1001])
        cacher.remove_igdb_id(1001)
        assert cacher.get_stores_for_igdb_id(1001) is None

    def test_empty_mappings(self, tmp_path):
        db = tmp_path / "test.db"
        cacher = ResolversCacher(db)
        assert cacher.get_all_mappings() == {}


# ── DesconocidosCacher ──────────────────────────────────────────

class TestDesconocidosCacher:
    def test_save_and_is_unknown(self, tmp_path):
        cacher = DesconocidosCacher(db_path=tmp_path / "unknown.db")
        cacher.save_unknown("steam", "Unknown Game", "99999")
        assert cacher.is_unknown("steam", "99999") is True

    def test_get_all(self, tmp_path):
        cacher = DesconocidosCacher(db_path=tmp_path / "unknown.db")
        cacher.save_unknown("steam", "Game A", "111")
        cacher.save_unknown("epic", "Game B", "222")
        all_u = cacher.get_all()
        assert len(all_u) == 2

    def test_remove(self, tmp_path):
        cacher = DesconocidosCacher(db_path=tmp_path / "unknown.db")
        cacher.save_unknown("steam", "Game", "111")
        cacher.remove_unknown("steam", "111")
        assert cacher.is_unknown("steam", "111") is False

    def test_get_by_store(self, tmp_path):
        cacher = DesconocidosCacher(db_path=tmp_path / "unknown.db")
        cacher.save_unknown("steam", "Game A", "111")
        cacher.save_unknown("steam", "Game B", "222")
        cacher.save_unknown("epic", "Game C", "333")
        steam_unknowns = cacher.get_by_store("steam")
        assert len(steam_unknowns) == 2

    def test_clear(self, tmp_path):
        cacher = DesconocidosCacher(db_path=tmp_path / "unknown.db")
        cacher.save_unknown("steam", "Game", "111")
        cacher.clear()
        assert cacher.count() == 0

    def test_duplicate_save(self, tmp_path):
        cacher = DesconocidosCacher(db_path=tmp_path / "unknown.db")
        cacher.save_unknown("steam", "Game", "111")
        cacher.save_unknown("steam", "Game Updated", "111")
        assert cacher.count() == 1


# ── LibraryCacher ───────────────────────────────────────────────

class TestLibraryCacher:
    def test_set_and_get_status(self, tmp_path):
        cacher = LibraryCacher(db_path=tmp_path / "library.db")
        cacher.set_status(1, finished=True, hidden=False,
                          backlog=True, favorite=False)
        status = cacher.get_status(1)
        assert status["finished"] is True
        assert status["hidden"] is False
        assert status["backlog"] is True
        assert status["favorite"] is False

    def test_get_all_statuses(self, tmp_path):
        cacher = LibraryCacher(db_path=tmp_path / "library.db")
        cacher.set_status(1, finished=True, hidden=False,
                          backlog=True, favorite=False)
        cacher.set_status(2, finished=False, hidden=True,
                          backlog=False, favorite=True)
        all_s = cacher.get_all_statuses()
        assert len(all_s) == 2
        assert all_s[1]["finished"] is True
        assert all_s[2]["hidden"] is True

    def test_nonexistent_returns_empty(self, tmp_path):
        cacher = LibraryCacher(db_path=tmp_path / "library.db")
        assert cacher.get_status(999) == {}

    def test_update_partial(self, tmp_path):
        cacher = LibraryCacher(db_path=tmp_path / "library.db")
        cacher.set_status(1, finished=True, hidden=False,
                          backlog=False, favorite=False)
        cacher.set_status(1, finished=False, hidden=True,
                          backlog=False, favorite=False)
        status = cacher.get_status(1)
        assert status["finished"] is False
        assert status["hidden"] is True

    def test_all_flags_default_false(self, tmp_path):
        cacher = LibraryCacher(db_path=tmp_path / "library.db")
        cacher.set_status(1, finished=True, hidden=False,
                          backlog=False, favorite=False)
        status = cacher.get_status(1)
        assert status.get("backlog") is False
        assert status.get("favorite") is False


# ── Centinela de duración HLTB ──────────────────────────────────

class TestHLTBSentinel:
    """
    `duration_hours = 0` significaba a la vez "dura cero horas" y "HLTB no
    encontró nada". Ahora lo desconocido es NULL y el intento fallido se
    registra aparte en `hltb_checked`.
    """

    def test_mark_and_read_checked_flag(self, tmp_path):
        cacher = ExtrasCacher(tmp_path / "p.db")
        assert cacher.is_hltb_checked(1) is False

        cacher.mark_hltb_checked(1)

        assert cacher.is_hltb_checked(1) is True
        assert cacher.get_hltb_checked_ids() == {1}

    def test_marking_checked_preserves_other_extras(self, tmp_path):
        cacher = ExtrasCacher(tmp_path / "p.db")
        cacher.save_extras(1, steamdb_score=88.0, review_pos=900)

        cacher.mark_hltb_checked(1)

        extras = cacher.get_extras(1)
        assert extras["steamdb_score"] == 88.0
        assert extras["review_pos"] == 900
        assert extras["hltb_checked"] == 1

    def test_legacy_zero_durations_are_migrated(self, tmp_path):
        import sqlite3
        db = tmp_path / "p.db"

        # Base antigua: sin hltb_checked y con el centinela 0
        with sqlite3.connect(db) as conn:
            conn.execute(
                "CREATE TABLE extras (id_igdb INTEGER PRIMARY KEY,"
                " duration_hours REAL, steam_review INTEGER, steamdb_score REAL,"
                " review_pos INTEGER, review_neg INTEGER)"
            )
            conn.executemany(
                "INSERT INTO extras (id_igdb, duration_hours) VALUES (?, ?)",
                [(1, 0.0), (2, 12.5)],
            )
            conn.commit()

        cacher = ExtrasCacher(db)

        # El 0 pasa a desconocido, pero se recuerda que ya se consultó
        assert cacher.get_extras(1)["duration_hours"] is None
        assert cacher.is_hltb_checked(1) is True
        # Una duración real no se toca
        assert cacher.get_extras(2)["duration_hours"] == 12.5
        assert cacher.is_hltb_checked(2) is False

    def test_bulk_save_matches_individual_save(self, tmp_path):
        cacher = ExtrasCacher(tmp_path / "p.db")

        cacher.save_extras_bulk([
            (1, 10.0, 8, 88.0, 900, 100),
            (2, 20.0, 9, 92.0, 500, 20),
        ])

        assert cacher.get_extras(1)["duration_hours"] == 10.0
        assert cacher.get_extras(2)["steamdb_score"] == 92.0

    def test_bulk_save_ignores_empty_input(self, tmp_path):
        cacher = ExtrasCacher(tmp_path / "p.db")
        cacher.save_extras_bulk([])
        assert cacher.get_all_extras() == {}


class TestCacherResilience:
    def test_transient_query_error_does_not_disable_the_cacher(self, tmp_path):
        """
        Un fallo puntual de SQLite dejaba `_available` en False para el resto
        de la sesión, tumbando la carga entera.
        """
        cacher = IGDBCacher(tmp_path / "p.db")
        cacher.save_game(SAMPLE_GAME)

        # Consulta inválida contra una tabla inexistente
        assert cacher._query("SELECT * FROM no_existe") == []

        assert cacher.available is True
        assert cacher.get_game(1234) is not None
