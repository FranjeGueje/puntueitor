import logging
import math
from dataclasses import replace

import requests

from puntueitor.core import Game
from puntueitor.core.cachers.igdb_cacher import IGDBCacher
from puntueitor.core.protocols import GameEnricher

logger = logging.getLogger(__name__)

STEAM_REVIEWS_URL = "https://store.steampowered.com/appreviews/{steam_id}"
REQUEST_TIMEOUT = 10


class SteamScoreEnricher(GameEnricher):
    """Añade la puntuación bayesiana de reseñas de Steam (estilo SteamDB)."""

    def __init__(
        self,
        overwrite: bool = False,
        igdb_cacher: IGDBCacher | None = None,
        extras_cacher=None,
    ):
        self.overwrite = overwrite
        self.igdb_cacher = igdb_cacher
        # Sin esto las notas se volvían a pedir a Steam en cada recarga: el
        # `replace` de abajo solo cambia el juego en memoria, y el guardado de
        # `refresh_library` ya ha pasado cuando los enrichers terminan.
        self.extras_cacher = extras_cacher

    def enrich(self, game: Game) -> Game:
        if (
            game.steamdb_score is not None
            and game.steam_review is not None
            and not self.overwrite
        ):
            return game

        steam_id = self._get_steam_id(game)
        if not steam_id:
            return game

        scores = self._fetch_score(steam_id)
        if scores is None:
            # Fallo de red o respuesta inservible: conservamos lo que ya
            # tuviera el juego en lugar de sobreescribirlo con None.
            return game

        steamdb, review, pos, neg = scores
        if self.extras_cacher is not None:
            self.extras_cacher.save_extras(
                game.igdb_id, steam_review=review, steamdb_score=steamdb,
                review_pos=pos, review_neg=neg,
            )
        return replace(
            game,
            steamdb_score=steamdb,
            steam_review=review,
            review_pos=pos,
            review_neg=neg,
        )

    def _get_steam_id(self, game: Game) -> str | None:
        steam_id = game.stores.get("steam")
        if steam_id:
            return steam_id

        if self.igdb_cacher:
            raw = self.igdb_cacher.get_game(game.igdb_id)
            if raw and raw.get("steam_id"):
                return str(raw["steam_id"])

        return None

    @staticmethod
    def _bayesian_score(positive: int, negative: int) -> float | None:
        """Media de reseñas corregida por volumen (fórmula de SteamDB)."""
        total = positive + negative
        if total <= 0:
            return None
        average = positive / total
        score = average - (average - 0.5) * (2 ** (-math.log10(total + 1)))
        return round(score * 100, 2)

    def _fetch_score(
        self, steam_id: str
    ) -> tuple[float | None, int | None, int | None, int | None] | None:
        """
        Devuelve (steamdb_score, review_score, positivas, negativas),
        o None si la consulta falla.
        """
        try:
            response = requests.get(
                STEAM_REVIEWS_URL.format(steam_id=steam_id),
                params={
                    "json": 1,
                    "language": "all",
                    "filter": "all",
                    "review_type": "all",
                    "purchase_type": "all",
                    "num_per_page": 0,
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            summary = response.json().get("query_summary", {})
        except Exception as e:
            from puntueitor.core.diagnostics import describe_error
            # A DEBUG: esto se llama una vez por juego y un fallo suelto no
            # rompe nada (se conserva la nota que ya hubiera). Lo que sí se
            # ve, si falla en serie, es el resumen de la carga.
            logger.debug(
                f"sin reseñas de Steam para la app {steam_id}: "
                f"{describe_error(e, 'Steam')}"
            )
            return None

        if not summary.get("total_reviews"):
            return None

        positive = summary.get("total_positive", 0)
        negative = summary.get("total_negative", 0)

        return (
            self._bayesian_score(positive, negative),
            summary.get("review_score"),
            positive,
            negative,
        )
