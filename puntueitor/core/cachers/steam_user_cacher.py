import logging
import sqlite3
import json
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

class SteamUserCacher:
    """
    Caché relacional de juegos de Steam, por usuario.
    La BBDD se llama {steam_user_id}.sqlite y vive en cache_dir.
    Tiene una tabla `owned_games` con las columnas del endpoint GetOwnedGames.
    """

    def __init__(self, steam_user_id: int, cache_dir: str | Path | None = None):
        new_default_dir = Path.home() / ".cache" / "puntueitor"
        
        if cache_dir:
            base_dir = Path(cache_dir)
        else:
            base_dir = new_default_dir
            
        base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = base_dir / f"{steam_user_id}.sqlite"

        # Migración: Si no existe en la nueva ruta pero sí en la antigua default (./cache)
        old_default_path = Path.cwd() / "cache" / f"{steam_user_id}.sqlite"
        if not self.db_path.exists() and old_default_path.exists():
            try:
                import shutil
                shutil.move(str(old_default_path), str(self.db_path))
            except Exception:
                pass # Si falla el movimiento, se creará una nueva DB
        
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("""
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
                )
            """)
            conn.commit()

    def get_all_games(self) -> list[dict] | None:
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM owned_games")
            rows = cursor.fetchall()
            if not rows:
                return None
            result = []
            for row in rows:
                d = dict(row)
                if d.get("content_descriptorids"):
                    d["content_descriptorids"] = json.loads(d["content_descriptorids"])
                result.append(d)
            return result

    def save_games(self, games: list[dict]) -> None:
        sanitized = []
        for g in games:
            appid = g.get("appid")
            name = g.get("name")

            if not isinstance(appid, int) or appid <= 0:
                logger.warning(f"Skipping invalid game: invalid appid {appid}")
                continue

            if not isinstance(name, str):
                logger.warning(f"Skipping game with appid {appid}: invalid name type")
                continue

            sanitized.append({
                "appid": appid,
                "name": name[:500] if len(name) > 500 else name,
                "playtime_forever": g.get("playtime_forever", 0) or 0,
                "img_icon_url": g.get("img_icon_url"),
                "playtime_windows_forever": g.get("playtime_windows_forever", 0) or 0,
                "playtime_mac_forever": g.get("playtime_mac_forever", 0) or 0,
                "playtime_linux_forever": g.get("playtime_linux_forever", 0) or 0,
                "playtime_deck_forever": g.get("playtime_deck_forever", 0) or 0,
                "rtime_last_played": g.get("rtime_last_played", 0) or 0,
                "content_descriptorids": json.dumps(g.get("content_descriptorids") or []),
                "playtime_disconnected": g.get("playtime_disconnected", 0) or 0,
                "has_community_visible_stats": int(bool(g.get("has_community_visible_stats", False))),
            })

        if not sanitized:
            logger.warning("No valid games to save")
            return

        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("DELETE FROM owned_games")
            conn.executemany("""
                INSERT INTO owned_games (
                    appid, name, playtime_forever, img_icon_url,
                    playtime_windows_forever, playtime_mac_forever,
                    playtime_linux_forever, playtime_deck_forever,
                    rtime_last_played, content_descriptorids,
                    playtime_disconnected, has_community_visible_stats
                ) VALUES (
                    :appid, :name, :playtime_forever, :img_icon_url,
                    :playtime_windows_forever, :playtime_mac_forever,
                    :playtime_linux_forever, :playtime_deck_forever,
                    :rtime_last_played, :content_descriptorids,
                    :playtime_disconnected, :has_community_visible_stats
                )
            """, sanitized)
            conn.commit()
