from datetime import datetime, timezone, date

from puntueitor.core import Game


class IGMapperGame:
    """ Mapeador de datos en bruto devueltos por IGDBEngine
    y transformados y mapeados a Game
    """

    @staticmethod
    def map_to_game(raw: dict) -> Game:
        igdb_id = raw["id"]
        title = raw["name"]

        genres_raw = raw.get("genres") or []
        genres = tuple(
            g["name"] for g in genres_raw
            if isinstance(g, dict) and "name" in g
        )

        critic_score = raw.get("aggregated_rating")
        user_score = raw.get("rating")

        cover_raw = raw.get("cover")
        cover_t = cover_raw.get("url") if cover_raw else None
        cover_url = "https:" + cover_t.replace("t_thumb", "t_cover_big") if cover_t else None
        
        storyline = raw.get("storyline")

        # IGDB no da duración → esto vendrá de enrichers
        duration_hours = None

        # ✅ release_date correcta
        release_date: date | None = None
        ts = raw.get("first_release_date")
        if isinstance(ts, (int, float)):
            try:
                release_date = datetime.fromtimestamp(
                    ts, tz=timezone.utc
                ).date()
            except (OSError, OverflowError, ValueError):
                release_date = None

        return Game(
            igdb_id=igdb_id,
            title=title,
            genres=genres,
            storyline=storyline,
            critic_score=critic_score,
            user_score=user_score,
            cover_url=cover_url,
            release_date=release_date,
            duration_hours=duration_hours,
            stores={},
        )

    @staticmethod
    def map_to_list(raw_list: list[dict]) -> list[Game]:
        return [IGMapperGame.map_to_game(raw) for raw in raw_list]
