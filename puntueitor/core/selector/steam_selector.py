from collections.abc import Sequence
import logging

from puntueitor.core.selector.base_selector import GameSelector
from puntueitor.core.models import Game, SelectionContext

logger = logging.getLogger(__name__)


class SteamSelector(GameSelector):

    def __init__(self) -> None:
        super().__init__()

    def select(
        self,
        candidates: Sequence[Game],
        ctx: SelectionContext,
    ) -> Game | None:
        """
        Selecciona el mejor Game basándose en score total y disponibilidad de datos.
        Prioriza: 1) score total más alto, 2) más campos completados.
        """
        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0]

        best_game = None
        best_score = -1.0
        best_data_completeness = 0

        for game in candidates:
            game_score = game.total_score
            data_completeness = sum(1 for v in (
                game.critic_score,
                game.user_score,
                game.duration_hours,
                game.cover_url
            ) if v is not None)

            if game_score is None:
                game_score = 0.0

            if (game_score > best_score) or (
                game_score == best_score and data_completeness > best_data_completeness
            ):
                best_game = game
                best_score = game_score
                best_data_completeness = data_completeness

        logger.debug(f"Selected game '{best_game.title}' with score {best_score}")
        return best_game

