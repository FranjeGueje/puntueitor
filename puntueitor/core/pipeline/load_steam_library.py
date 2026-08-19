import logging
from collections.abc import Callable, Generator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from puntueitor.core.diagnostics import describe_error
from puntueitor.core.igdb.service import IGDBService
from puntueitor.core.models import Game, Stores
from puntueitor.core.models.selection_context import SelectionContext
from puntueitor.core.protocols import GameEnricher
from puntueitor.core.resolvers.steam_resolver import SteamIGDBResolver
from puntueitor.core.resolvers.gog_resolver import GOGResolver
from puntueitor.core.resolvers.epic_resolver import EpicResolver
from puntueitor.core.resolvers.amazon_resolver import AmazonResolver
from puntueitor.core.selector.steam_selector import SteamSelector
from puntueitor.core.config import ConfigManager
from puntueitor.core import paths
from puntueitor.core.providers import LibraryProvider, build_providers

logger = logging.getLogger(__name__)

CACHEABLE_EXTRAS = (
    "duration_hours", "steam_review", "steamdb_score", "review_pos", "review_neg",
)


def _apply_cached_extras(game: Game, extras_cache: dict[int, dict] | None) -> Game:
    """Rellena desde la caché los extras ya conocidos del juego."""
    if not extras_cache:
        return game

    cached = extras_cache.get(game.igdb_id)
    if not cached:
        return game

    known = {
        field: cached[field]
        for field in CACHEABLE_EXTRAS
        if cached.get(field) is not None
    }
    return replace(game, **known) if known else game


def _run_enrichment(
    game: Game,
    enrichers: Sequence[GameEnricher],
    completed_callback: Callable[[Game], None],
    extras_cache: dict[int, dict] | None = None,
) -> None:
    """Ejecuta el enrichment en background y llama al callback cuando termina."""
    result = _apply_cached_extras(game, extras_cache)

    # Siempre se pasa por los enrichers: cada uno decide si hay algo que
    # completar. Antes, tener un solo campo en caché cortaba aquí y dejaba el
    # resto sin enriquecer para siempre.
    for enricher in enrichers:
        try:
            result = enricher.enrich(result)
        except Exception as e:
            logger.debug(
                f"{type(enricher).__name__} failed for '{result.title}': {e}"
            )
            continue

    completed_callback(result)


def load_library(
    engine: IGDBService,
    providers: dict[Stores, LibraryProvider] | None = None,
    refresh: bool = False,
    force_store_refresh: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
    enrichers: Sequence[GameEnricher] | None = None,
    enrichment_callback: Callable[[Game], None] | None = None,
    extras_cache: dict[int, dict] | None = None,
) -> Generator[Game, None, None]:
    """
    Carga juegos de múltiples tiendas (Steam, GOG, Epic, Amazon).

    Va emitiendo cada `Game` según se resuelve. Si se pasan enrichers, los
    lanza en segundo plano y cierra su pool al terminar sin esperarlos: los
    resultados siguen llegando por `enrichment_callback`.
    """
    config = ConfigManager().get
    # Un proveedor por tienda activa. Que la tienda esté en el diccionario ya
    # significa que el usuario la quiere; no hace falta una segunda lista.
    if providers is None:
        providers = build_providers(config)

    CACHE_RESOLVERS = paths.main_db()
    steam_selector = SteamSelector()

    executor = ThreadPoolExecutor(max_workers=4) if enrichers else None

    def process_game(raw_item: dict, resolver, store_name: str, cuenta: dict) -> Game | None:
        """Resuelve un juego crudo y elige el mejor candidato."""
        title = raw_item.get("title") or raw_item.get("name") or "Unknown"
        try:
            games = resolver.resolve(raw=raw_item, refresh=refresh)
            if not games:
                cuenta["sin_resolver"] += 1
                return None
            cuenta["resueltos"] += 1
            return steam_selector.select(games, SelectionContext(title=str(title)))
        except Exception as e:
            cuenta["errores"] += 1
            # El primero con traza, para poder investigar; los demás solo
            # contados. Cuando IGDB no responde fallan los mil juegos, y mil
            # tracebacks idénticos hacen el log ilegible justo cuando más
            # falta hace leerlo.
            if cuenta["errores"] == 1:
                logger.warning(
                    f"[{store_name}] falló '{title}': "
                    f"{describe_error(e, 'IGDB')}",
                    exc_info=True,
                )
            else:
                logger.debug(f"[{store_name}] falló '{title}': {e}")
            return None

    def submit_enrichment(game: Game) -> None:
        if enrichers and executor and enrichment_callback:
            executor.submit(
                _run_enrichment, game, enrichers, enrichment_callback, extras_cache,
            )

    def load_store(
        label: str,
        resolver,
        raw_items: Sequence[dict],
    ) -> Generator[Game, None, None]:
        """Resuelve los juegos crudos de una tienda, emitiéndolos uno a uno."""
        total = len(raw_items)
        cuenta = {"resueltos": 0, "sin_resolver": 0, "errores": 0}
        for index, raw_item in enumerate(raw_items, start=1):
            title = raw_item.get("title") or raw_item.get("name") or "Unknown"
            if progress_callback:
                progress_callback(index, total, f"[{label}] {title}")

            game = process_game(raw_item, resolver, label, cuenta)
            if game:
                submit_enrichment(game)
                yield game

        # El resumen es lo que hace el log legible: mil líneas sueltas no
        # dicen si la carga fue bien, y una sola sí.
        resumen = (
            f"{label}: {total} juegos en la tienda, {cuenta['resueltos']} "
            f"identificados, {cuenta['sin_resolver']} sin identificar"
        )
        if cuenta["errores"]:
            logger.warning(f"{resumen}, {cuenta['errores']} con ERRORES")
        else:
            logger.info(resumen)

    #: El resolver que sabe leer los crudos de cada tienda.
    RESOLVERS = {
        Stores.STEAM: SteamIGDBResolver,
        Stores.GOG: GOGResolver,
        Stores.EPIC: EpicResolver,
        Stores.AMAZON: AmazonResolver,
    }

    if not providers:
        logger.warning(
            "no hay ninguna tienda activa: no hay nada que cargar "
            "(Opciones → Configuración)"
        )

    total_emitidos = 0

    try:
        for store, provider in providers.items():
            label = provider.LABEL
            try:
                # `fetch` no lanza: ya cae solo a la copia guardada y lo
                # explica en el log. El try es por si falla el resolver.
                raw_items = provider.fetch(refresh=refresh or force_store_refresh)
                if not raw_items:
                    continue
                resolver = RESOLVERS[store](igdb=engine, cache_file=CACHE_RESOLVERS)
            except Exception as e:
                logger.warning(f"no se pudo leer {label}: {describe_error(e, label)}")
                continue

            for game in load_store(label, resolver, raw_items):
                total_emitidos += 1
                yield game
    finally:
        # La última línea, y la que se mira primero: si aquí pone cero, todo
        # lo de arriba explica por qué.
        if total_emitidos:
            logger.info(f"Carga terminada: {total_emitidos} juegos")
        else:
            logger.warning(
                "Carga terminada SIN NINGÚN JUEGO. Los avisos anteriores "
                "dicen por qué (credenciales, conexión o tiendas sin datos)"
            )

        # No esperamos a los enrichers: siguen escribiendo por el callback.
        if executor:
            executor.shutdown(wait=False)
