import logging
from abc import ABC, abstractmethod
from dataclasses import replace

from puntueitor.core.cachers.extras_cacher import ExtrasCacher
from puntueitor.core.protocols import GameEnricher
from puntueitor.core import Game
from puntueitor.core.raw.howlongtobeat.hltb_entry import HLTBEntry

logger = logging.getLogger(__name__)


class HLTBClient(ABC):
    """
    Thin wrapper over howlongtobeat API / library.
    Returns raw HLTBEntry objects.
    """

    @abstractmethod
    def search(self, title: str) -> HLTBEntry | None:
        ...


class HLTBEnricher(GameEnricher):
    """
    Añade la duración estimada de HowLongToBeat.

    Cuando no encuentra el juego deja `duration_hours` en None ("desconocido")
    y lo anota en `extras.hltb_checked` para no repetir la búsqueda en cada
    arranque. Antes escribía 0, que los scorers interpretaban como una duración
    real de cero horas y colocaba esos juegos en lo más alto del ranking.

    Y cuando SÍ lo encuentra, lo guarda. Parece obvio y no lo era: durante
    mucho tiempo solo se persistían los fallos, así que los aciertos se
    consultaban una y otra vez en cada recarga —los mismos juegos, con el
    mismo resultado— y el dato se perdía al cerrar. El guardado que hay en
    `refresh_library` no llega a tiempo: los enrichers corren en un pool
    aparte y terminan después de que el juego haya pasado por ahí.
    """

    def __init__(
        self,
        client: HLTBClient,
        min_similarity: float = 0.6,
        overwrite: bool = False,
        extras_cacher: ExtrasCacher | None = None,
    ):
        assert 0.0 <= min_similarity <= 1.0
        self.client = client
        self.min_similarity = min_similarity
        self.overwrite = overwrite
        self.extras_cacher = extras_cacher

    def _mark_checked(self, game: Game) -> None:
        if self.extras_cacher is not None:
            self.extras_cacher.mark_hltb_checked(game.igdb_id)

    def _save(self, game: Game, duration: float) -> None:
        """
        Guarda la duración averiguada para no volver a preguntarla nunca.

        `save_extras` hace UPSERT con COALESCE, así que pasar solo la duración
        no toca las notas de Steam que hubiera en esa misma fila.
        """
        if self.extras_cacher is not None:
            self.extras_cacher.save_extras(game.igdb_id, duration_hours=duration)

    def enrich(self, game: Game) -> Game:
        if not self.overwrite:
            if game.duration_hours is not None:
                return game
            if self.extras_cacher and self.extras_cacher.is_hltb_checked(game.igdb_id):
                logger.debug(f"HLTB already checked without result for {game.title}")
                return game

        try:
            entry = self.client.search(game.title)
        except Exception as e:
            # Fallo transitorio: no lo marcamos como comprobado para poder
            # reintentar en la siguiente pasada.
            from puntueitor.core.diagnostics import describe_error
            logger.warning(
                f"no se pudo consultar la duración de '{game.title}': "
                f"{describe_error(e, 'HowLongToBeat')}"
            )
            return game

        if not entry:
            logger.debug(f"No HLTB entry found for {game.title}")
            self._mark_checked(game)
            return game

        if entry.similarity < self.min_similarity:
            logger.debug(
                f"HLTB similarity too low for {game.title}: "
                f"{entry.similarity} < {self.min_similarity}"
            )
            self._mark_checked(game)
            return game

        # Priorizar main_story, luego main_extra
        duration = entry.main_story if entry.main_story else entry.main_extra

        if duration is None or duration <= 0:
            logger.debug(f"HLTB duration not found for {game.title}")
            self._mark_checked(game)
            return game

        logger.info(f"Enriched {game.title} with {duration}h from HLTB")
        self._save(game, duration)
        return replace(game, duration_hours=duration)
