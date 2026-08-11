# Convertir raw inputs (Steam, Epic, etc.) en una Library consistente de Game.
import logging
from collections.abc import Iterable, Sequence, Callable

from puntueitor.core.models import Game, Library, ScoringContext
from puntueitor.core.resolvers.base_resolver import BaseResolver
from puntueitor.core.selector.base_selector import GameSelector
from puntueitor.core.services.library_ops import add_games

logger = logging.getLogger(__name__)


class LibraryBuilder:
    """
    Orquesta la construcción de una Library a partir de inputs crudos.
    """

    def __init__(
        self,
        *,
        resolvers: Sequence[BaseResolver],
        selector: GameSelector,
    ) -> None:
        self.resolvers = resolvers
        self.selector = selector

    def build(
        self,
        raws: Iterable[dict],
        *,
        context_factory: Callable[[dict], ScoringContext] | None = None,
        initial: Library | None = None,
    ) -> Library:
        """
        Construye una Library a partir de raws.
        """
        library = initial or Library.from_iterable(())
        selected_games: list[Game] = []

        for raw in raws:
            context = (
                context_factory(raw)
                if context_factory
                else ScoringContext()
            )

            candidates: list[Game] = []

            for resolver in self.resolvers:
                try:
                    candidates.extend(resolver.resolve(raw))
                except Exception as e:
                    logger.warning(
                        f"{type(resolver).__name__} failed to resolve a game: {e}"
                    )
                    continue

            selected = self.selector.select(candidates=candidates, ctx=context)
            if selected is None:
                continue

            selected_games.append(selected)

        # Una sola reconstrucción de la Library en vez de una por juego.
        return add_games(library, selected_games)
