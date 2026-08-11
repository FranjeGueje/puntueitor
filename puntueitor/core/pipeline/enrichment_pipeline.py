#Tomar una Library y devolver otra Library con juegos enriquecidos.
import logging
from collections.abc import Sequence

from puntueitor.core.protocols import GameEnricher
from puntueitor.core.models import Game, Library

logger = logging.getLogger(__name__)


class EnrichmentPipeline:
    """
    Aplica una secuencia de GameEnrichers a una Library.
    """

    def __init__(
        self,
        enrichers: Sequence[GameEnricher],
    ) -> None:
        self.enrichers = enrichers

    def enrich(
        self,
        library: Library,
    ) -> Library:
        enriched_games: list[Game] = []

        for game in library:
            current = game
            for enricher in self.enrichers:
                try:
                    current = enricher.enrich(current)
                except Exception as e:
                    # Contrato: los enrichers nunca deben romper la carga, pero
                    # tragarse el fallo en silencio ocultaba enrichers rotos.
                    logger.warning(
                        f"{type(enricher).__name__} failed for '{current.title}': {e}"
                    )
                    continue
            enriched_games.append(current)

        return Library.from_iterable(enriched_games)
