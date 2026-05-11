from collections.abc import Sequence
import logging

from puntueitor.core.selector.base_selector import GameSelector
from puntueitor.core.scoring.atomic import BasicScoreScorer
from puntueitor.core.protocols import GameScorer
from puntueitor.core.models import Game, SelectionContext, ScoringContext

logger = logging.getLogger(__name__)


class SteamSelector(GameSelector):

    def __init__(self, scorer: GameScorer | None = None) -> None:
        super().__init__()
        self.scorer = scorer or BasicScoreScorer()
        self._scoring_ctx = ScoringContext()  # Contexto por defecto para selección

    def select(
        self,
        candidates: Sequence[Game] | None,
        ctx: SelectionContext,
    ) -> Game | None:
        """
        Selecciona el mejor Game basándose en score y disponibilidad de datos.
        """
        if not candidates:
            return None

        try:
            candidates = list(candidates)
        except TypeError:
            return None

        if len(candidates) == 0:
            return None

        if len(candidates) == 1:
            return candidates[0]

        best_game = None
        best_score = -1.0
        best_data_completeness = 0

        for game in candidates:
            # Usamos el scorer inyectado en lugar de la propiedad del modelo
            game_score = self.scorer.score(game, self._scoring_ctx)
            
            data_completeness = sum(1 for v in (
                game.critic_score,
                game.user_score,
                game.duration_hours,
                game.cover_url
            ) if v is not None)

            if (game_score > best_score) or (
                game_score == best_score and data_completeness > best_data_completeness
            ):
                best_game = game
                best_score = game_score
                best_data_completeness = data_completeness

        logger.debug(f"Selected game '{best_game.title}' with score {best_score}")
        return best_game

