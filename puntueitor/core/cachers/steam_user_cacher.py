import json
import logging
import shutil
from pathlib import Path

from puntueitor.core.cachers.base_cacher import BaseCacher, CACHE_DB

logger = logging.getLogger(__name__)

_COLUMNS = (
    "appid", "name", "playtime_forever", "img_icon_url",
    "playtime_windows_forever", "playtime_mac_forever",
    "playtime_linux_forever", "playtime_deck_forever",
    "rtime_last_played", "content_descriptorids",
    "playtime_disconnected", "has_community_visible_stats",
)

_INSERT_GAMES = f"""
    INSERT INTO owned_games ({", ".join(_COLUMNS)})
    VALUES ({", ".join(f":{c}" for c in _COLUMNS)})
"""

_PLAYTIME_FIELDS = (
    "playtime_forever", "playtime_windows_forever", "playtime_mac_forever",
    "playtime_linux_forever", "playtime_deck_forever", "rtime_last_played",
    "playtime_disconnected",
)


class SteamUserCacher(BaseCacher):
    """
    Caché de la lista de juegos en propiedad de un usuario de Steam.

    La BBDD se llama {steam_user_id}.sqlite y vive en cache_dir.
    """

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS owned_games (
            appid                       INTEGER PRIMARY KEY,
            name                        TEXT,
            playtime_forever            INTEGER,
            img_icon_url                TEXT,
            playtime_windows_forever    INTEGER,
            playtime_mac_forever        INTEGER,
            playtime_linux_forever      INTEGER,
            playtime_deck_forever       INTEGER,
            rtime_last_played           INTEGER,
            content_descriptorids       JSON,
            playtime_disconnected       INTEGER,
            has_community_visible_stats INTEGER
        );
    """

    def __init__(self, steam_user_id: int, cache_dir: str | Path | None = None):
        base_dir = Path(cache_dir) if cache_dir else CACHE_DB.parent
        db_path = base_dir / f"{steam_user_id}.sqlite"

        # Migración desde la antigua ubicación relativa ./cache
        old_path = Path.cwd() / "cache" / f"{steam_user_id}.sqlite"
        if not db_path.exists() and old_path.exists():
            try:
                base_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(db_path))
            except Exception as e:
                logger.warning(f"Could not migrate steam cache from {old_path}: {e}")

        super().__init__(db_path)

    def get_all_games(self) -> list[dict] | None:
        rows = self._query("SELECT * FROM owned_games")
        if not rows:
            return None

        games = []
        for row in rows:
            game = dict(row)
            if game.get("content_descriptorids"):
                try:
                    game["content_descriptorids"] = json.loads(
                        game["content_descriptorids"]
                    )
                except (json.JSONDecodeError, TypeError):
                    game["content_descriptorids"] = []
            games.append(game)
        return games

    @staticmethod
    def _sanitize(game: dict) -> dict | None:
        appid = game.get("appid")
        name = game.get("name")

        if not isinstance(appid, int) or appid <= 0:
            logger.warning(f"Skipping invalid game: invalid appid {appid}")
            return None

        if not isinstance(name, str):
            logger.warning(f"Skipping game with appid {appid}: invalid name type")
            return None

        row = {
            "appid": appid,
            "name": name[:500],
            "img_icon_url": game.get("img_icon_url"),
            "content_descriptorids": json.dumps(
                game.get("content_descriptorids") or []
            ),
            "has_community_visible_stats": int(
                bool(game.get("has_community_visible_stats", False))
            ),
        }
        for field in _PLAYTIME_FIELDS:
            row[field] = game.get(field, 0) or 0
        return row

    def save_games(self, games: list[dict]) -> None:
        if not self._available:
            return

        sanitized = [row for row in map(self._sanitize, games) if row is not None]
        if not sanitized:
            logger.warning("No valid games to save")
            return

        try:
            conn = self._connect()
            with conn:
                conn.execute("DELETE FROM owned_games")
                conn.executemany(_INSERT_GAMES, sanitized)
        except Exception as e:
            logger.error(f"Error saving owned games to {self.db_path}: {e}")
