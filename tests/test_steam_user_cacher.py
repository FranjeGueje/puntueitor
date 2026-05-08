import os
import tempfile
import pytest

from puntueitor.core.cachers.steam_user_cacher import SteamUserCacher


class TestSteamUserCacher:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.user_id = 12345

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_get_games(self):
        cacher = SteamUserCacher(self.user_id, self.temp_dir)

        games = [
            {
                "appid": 10,
                "name": "Game One",
                "playtime_forever": 120,
                "img_icon_url": "icon1",
                "playtime_windows_forever": 100,
                "playtime_mac_forever": 10,
                "playtime_linux_forever": 10,
                "playtime_deck_forever": 120,
                "rtime_last_played": 1609459200,
                "content_descriptorids": [],
                "playtime_disconnected": 0,
                "has_community_visible_stats": True
            },
            {
                "appid": 20,
                "name": "Game Two",
                "playtime_forever": 240,
            }
        ]

        cacher.save_games(games)

        result = cacher.get_all_games()
        assert len(result) == 2
        assert result[0]["appid"] == 10
        assert result[0]["name"] == "Game One"
        assert result[1]["appid"] == 20

    def test_skips_invalid_appid(self):
        cacher = SteamUserCacher(self.user_id, self.temp_dir)

        games = [
            {"appid": "invalid", "name": "Should be skipped"},
            {"appid": 10, "name": "Valid Game"},
        ]

        cacher.save_games(games)

        result = cacher.get_all_games()
        assert len(result) == 1
        assert result[0]["name"] == "Valid Game"

    def test_skips_invalid_name_type(self):
        cacher = SteamUserCacher(self.user_id, self.temp_dir)

        games = [
            {"appid": 10, "name": 12345},
            {"appid": 20, "name": "Valid Game"},
        ]

        cacher.save_games(games)

        result = cacher.get_all_games()
        assert len(result) == 1
        assert result[0]["name"] == "Valid Game"

    def test_truncates_long_names(self):
        cacher = SteamUserCacher(self.user_id, self.temp_dir)

        long_name = "A" * 600
        games = [{"appid": 10, "name": long_name}]

        cacher.save_games(games)

        result = cacher.get_all_games()
        assert len(result[0]["name"]) == 500

    def test_handles_empty_list(self):
        cacher = SteamUserCacher(self.user_id, self.temp_dir)

        cacher.save_games([])

        result = cacher.get_all_games()
        assert result is None or result == []

    def test_get_all_games_returns_none_when_empty(self):
        cacher = SteamUserCacher(self.user_id, self.temp_dir)

        result = cacher.get_all_games()
        assert result is None