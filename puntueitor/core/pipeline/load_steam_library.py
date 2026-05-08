from puntueitor.core.igdb.service import IGDBService
from puntueitor.core.models import Library
from typing import Callable

from puntueitor.core.models.selection_context import SelectionContext
from puntueitor.core.resolvers.steam_resolver import SteamIGDBResolver
from puntueitor.core.selector.steam_selector import SteamSelector
from steampy.api.steam_api import SteamApi

from puntueitor.core.services.library_ops import add_game
from puntueitor.core.config import ConfigManager

def load_steam_library(
    engine: IGDBService,
    api_key: str | None = None,
    user: int | None = None,
    refresh: bool = False,
    force_store_refresh: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Library:
    config = ConfigManager().get
    api_key = api_key or config.steam_api_key
    user = user or config.steam_user_id

    CACHE_RESOLVERS="cache/resolvers.sqlite"
    library = Library.from_iterable(())
    steam_resolver = SteamIGDBResolver(igdb=engine, cache_file=CACHE_RESOLVERS)
    steam_selector = SteamSelector()
        
    steam = SteamApi()
    # force_store_refresh=True → siempre descarga de Steam API y actualiza store DB
    # refresh=True → adicionalmente bypasea caché de IGDB
    use_steam_cache = not (refresh or force_store_refresh)
    steam_games = steam.owned_games(api_key, user, use_cache=use_steam_cache)
    if steam_games:
        total = len(steam_games)
        for i, item in enumerate(steam_games):
            if progress_callback:
                progress_callback(i + 1, total, str(item.get("name")))
            games = steam_resolver.resolve(raw=item, refresh=refresh)
            better_game = steam_selector.select(games, SelectionContext(title=str(item.get("name"))))
            if better_game:
                library = add_game(library, better_game)
    
    return library

