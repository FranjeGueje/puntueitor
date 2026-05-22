import logging
from pathlib import Path
from typing import Callable, Generator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

logger = logging.getLogger(__name__)
from puntueitor.core.igdb.service import IGDBService
from puntueitor.core.models import Library, Game
from puntueitor.core.models.selection_context import SelectionContext
from puntueitor.core.protocols import GameEnricher
from puntueitor.core.resolvers.steam_resolver import SteamIGDBResolver
from puntueitor.core.resolvers.gog_resolver import GOGHeroicResolver
from puntueitor.core.resolvers.epic_resolver import EpicHeroicResolver
from puntueitor.core.resolvers.amazon_resolver import AmazonHeroicResolver
from puntueitor.core.selector.steam_selector import SteamSelector
from steampy.api.steam_api import SteamApi
from puntueitor.core.config import ConfigManager
from puntueitor.core.heroics import HeroicsLoader


def _run_enrichment(
    game: Game,
    enrichers: Sequence[GameEnricher],
    completed_callback: Callable[[Game], None],
    extras_cache: dict[int, dict] | None = None,
) -> None:
    """Ejecuta el enrichment en background y llama al callback cuando termina."""
    if extras_cache and game.igdb_id in extras_cache:
        cached = extras_cache[game.igdb_id]
        enriched = game
        if cached.get("duration_hours") is not None:
            enriched = replace(enriched, duration_hours=cached["duration_hours"])
        if cached.get("steam_score") is not None:
            enriched = replace(enriched, steam_score=cached["steam_score"])
        if cached.get("steam_review") is not None:
            enriched = replace(enriched, steam_review=cached["steam_review"])
        if enriched is not game:
            completed_callback(enriched)
            return
    result = game
    for enricher in enrichers:
        try:
            result = enricher.enrich(result)
        except Exception:
            continue
    completed_callback(result)


def load_library(
    engine: IGDBService,
    heroic_loader: HeroicsLoader | None = None,
    api_key: str | None = None,
    user: int | None = None,
    refresh: bool = False,
    force_store_refresh: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
    enrichers: Sequence[GameEnricher] | None = None,
    enrichment_callback: Callable[[Game], None] | None = None,
    extras_cache: dict[int, dict] | None = None,
) -> Generator[Game, None, None]:
    """Carga juegos de múltiples tiendas (Steam, GOG, Epic, Amazon)."""
    config = ConfigManager().get
    # Build stores list from new config fields
    stores = []
    if config.steam_is_active:
        stores.append("steam")
    if config.gog_is_active:
        stores.append("gog")
    if config.epic_is_active:
        stores.append("epic")
    if config.amazon_is_active:
        stores.append("amazon")

    api_key = api_key or config.steam_api_key
    user = user or config.steam_user_id

    CACHE_RESOLVERS = Path.home() / ".cache" / "puntueitor" / "puntueitor.db"
    steam_selector = SteamSelector()

    executor = ThreadPoolExecutor(max_workers=4) if enrichers else None
    games_loaded = []

    def process_game(raw_item: dict, resolver, store_name: str) -> Game | None:
        """Procesa un juego con su resolver y retorna el mejor."""
        try:
            title = raw_item.get("title") or raw_item.get("name", "")
            games = resolver.resolve(raw=raw_item, refresh=refresh)
            if not games:
                return None
            selected = steam_selector.select(games, SelectionContext(title=str(title)))
            return selected
        except Exception as e:
            title = raw_item.get("title") or raw_item.get("name", "Unknown")
            logger.warning(f"Error processing game from {store_name}: {e} for '{title}'", exc_info=True)
            return None

    def yield_or_store(game: Game) -> Game | None:
        """Yield el juego o lo guarda para enriquecimiento."""
        if game:
            if enrichers and executor and enrichment_callback:
                executor.submit(
                    _run_enrichment,
                    game,
                    enrichers,
                    enrichment_callback,
                    extras_cache,
                )
            return game
        return None

    # Cargar Steam
    if "steam" in stores and api_key and user:
        try:
            steam_resolver = SteamIGDBResolver(igdb=engine, cache_file=CACHE_RESOLVERS)
            steam = SteamApi()
            use_steam_cache = not (refresh or force_store_refresh)
            steam_games = steam.owned_games(api_key, user, use_cache=use_steam_cache)

            if steam_games:
                total = len(steam_games)
                for i, item in enumerate(steam_games):
                    title = str(item.get("name"))
                    if progress_callback:
                        progress_callback(i + 1, total, f"[Steam] {title}")

                    game = process_game(item, steam_resolver, "steam")
                    result = yield_or_store(game)
                    if result:
                        games_loaded.append(result)
                        yield result
        except Exception as e:
            logger.warning(f"Error loading games from Steam: {e}")

    heroic_path = None

    # Cargar GOG desde Heroic
    if "gog" in stores and heroic_loader:
        try:
            heroic_path = heroic_loader.find_heroic_path(config.heroic_path or None)
            if heroic_path:
                gog_resolver = GOGHeroicResolver(igdb=engine, cache_file=CACHE_RESOLVERS)
                gog_games = heroic_loader.get_gog_games(heroic_path)

                if gog_games:
                    total = len(gog_games)
                    for i, item in enumerate(gog_games):
                        title = item.get("title", "Unknown")
                        if progress_callback:
                            progress_callback(i + 1, total, f"[GOG] {title}")

                        game = process_game(item, gog_resolver, "gog")
                        result = yield_or_store(game)
                        if result:
                            games_loaded.append(result)
                            yield result
        except Exception as e:
            logger.warning(f"Error loading games from GOG: {e}")

    # Cargar Epic desde Heroic
    if "epic" in stores and heroic_loader:
        try:
            heroic_path = heroic_path or heroic_loader.find_heroic_path(config.heroic_path or None)
            if heroic_path:
                epic_resolver = EpicHeroicResolver(igdb=engine, cache_file=CACHE_RESOLVERS)
                epic_games = heroic_loader.get_epic_games(heroic_path)

                if epic_games:
                    total = len(epic_games)
                    for i, item in enumerate(epic_games):
                        title = item.get("title", "Unknown")
                        if progress_callback:
                            progress_callback(i + 1, total, f"[Epic] {title}")

                        game = process_game(item, epic_resolver, "epic")
                        result = yield_or_store(game)
                        if result:
                            games_loaded.append(result)
                            yield result
        except Exception as e:
            logger.warning(f"Error loading games from Epic: {e}")

    # Cargar Amazon desde Heroic
    if "amazon" in stores and heroic_loader:
        try:
            heroic_path = heroic_path or heroic_loader.find_heroic_path(config.heroic_path or None)
            if heroic_path:
                amazon_resolver = AmazonHeroicResolver(igdb=engine, cache_file=CACHE_RESOLVERS)
                amazon_games = heroic_loader.get_amazon_games(heroic_path)

                if amazon_games:
                    total = len(amazon_games)
                    for i, item in enumerate(amazon_games):
                        title = item.get("title", "Unknown")
                        if progress_callback:
                            progress_callback(i + 1, total, f"[Amazon] {title}")

                        game = process_game(item, amazon_resolver, "amazon")
                        result = yield_or_store(game)
                        if result:
                            games_loaded.append(result)
                            yield result
        except Exception as e:
            logger.warning(f"Error loading games from Amazon: {e}")

    yield executor


def load_steam_library(
    engine: IGDBService,
    api_key: str | None = None,
    user: int | None = None,
    refresh: bool = False,
    force_store_refresh: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
    enrichers: Sequence[GameEnricher] | None = None,
    enrichment_callback: Callable[[Game], None] | None = None,
) -> Generator[Game, None, None]:
    """Legacy: Carga solo juegos de Steam."""
    return load_library(
        engine=engine,
        api_key=api_key,
        user=user,
        refresh=refresh,
        force_store_refresh=force_store_refresh,
        progress_callback=progress_callback,
        enrichers=enrichers,
        enrichment_callback=enrichment_callback,
    )