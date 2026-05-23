import math
from dataclasses import replace

import requests

from puntueitor.core import Game
from puntueitor.core.cachers.igdb_cacher import IGDBCacher
from puntueitor.core.protocols import GameEnricher


class SteamScoreEnricher(GameEnricher):
    def __init__(
        self,
        overwrite: bool = False,
        igdb_cacher: IGDBCacher | None = None,
    ):
        self.overwrite = overwrite
        self.igdb_cacher = igdb_cacher

    def enrich(self, game: Game) -> Game:
        if game.steamdb_score is not None and game.steam_review is not None and not self.overwrite:
            return game

        steam_id = self._get_steam_id(game)
        if not steam_id:
            return game

        steamdb, review, pos, neg = self._fetch_score(steam_id)
        return replace(game, steamdb_score=steamdb, steam_review=review, review_pos=pos, review_neg=neg)

    def _get_steam_id(self, game: Game) -> str | None:
        sid = game.stores.get("steam") if hasattr(game.stores, "get") else None
        if sid:
            return sid
        if self.igdb_cacher:
            raw = self.igdb_cacher.get_game(game.igdb_id)
            if raw and raw.get("steam_id"):
                return str(raw["steam_id"])
        return None

    def _fetch_score(self, steam_id: str) -> tuple[float | None, int | None, int | None, int | None]:
        try:
            url = f"https://store.steampowered.com/appreviews/{steam_id}"
            params = {
                "json": 1,
                "language": "all",
                "filter": "all",
                "review_type": "all",
                "purchase_type": "all",
                "num_per_page": 0,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            summary = data.get("query_summary", {})
            total_positive = summary.get("total_positive", 0)
            total_negative = summary.get("total_negative", 0)
            total_reviews = summary.get("total_reviews", 0)
            review_score = summary.get("review_score")

            steamdb_score = None
            if total_reviews > 0:
                total = total_positive + total_negative
                average = total_positive / total
                score = average - (average - 0.5) * (2 ** (-math.log10(total + 1)))
                steamdb_score = round(score * 100, 2)

            return steamdb_score, review_score, total_positive, total_negative
        except Exception:
            pass
        return None, None, None, None
