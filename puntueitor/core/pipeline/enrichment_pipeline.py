#Tomar una Library y devolver otra Library con juegos enriquecidos.
from collections.abc import Sequence

from puntueitor.core.protocols import GameEnricher
from puntueitor.core.models import Game, Library


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
                except Exception:
                    # contrato: enrichers nunca deben romper
                    continue
            enriched_games.append(current)

        return Library.from_iterable(enriched_games)
