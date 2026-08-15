import logging
from collections.abc import Callable, Generator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from puntueitor.core.diagnostics import describe_error
from puntueitor.core.igdb.service import IGDBService
from puntueitor.core.models import Game
from puntueitor.core.models.selection_context import SelectionContext
from puntueitor.core.protocols import GameEnricher
from puntueitor.core.resolvers.steam_resolver import SteamIGDBResolver
from puntueitor.core.resolvers.gog_resolver import GOGHeroicResolver
from puntueitor.core.resolvers.epic_resolver import EpicHeroicResolver
from puntueitor.core.resolvers.amazon_resolver import AmazonHeroicResolver
from puntueitor.core.selector.steam_selector import SteamSelector
from steampy.api.steam_api import SteamApi
from puntueitor.core.config import ConfigManager
from puntueitor.core import paths
from puntueitor.core.heroics import HeroicsLoader

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
    """
    Carga juegos de múltiples tiendas (Steam, GOG, Epic, Amazon).

    Va emitiendo cada `Game` según se resuelve. Si se pasan enrichers, los
    lanza en segundo plano y cierra su pool al terminar sin esperarlos: los
    resultados siguen llegando por `enrichment_callback`.
    """
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

    def steam_items() -> Sequence[dict]:
        # Steam activa pero sin con qué preguntar. Antes esto devolvía la
        # tupla vacía sin decir nada, y el usuario se quedaba sin sus juegos
        # de Steam y sin ninguna pista de por qué.
        if not api_key:
            logger.warning(
                "Steam está activa pero no hay API key: no se cargará ningún "
                "juego de Steam (Opciones → Configuración)"
            )
            return ()
        if not user:
            logger.warning(
                "Steam está activa pero no hay Steam ID: no se cargará ningún "
                "juego de Steam (Opciones → Configuración)"
            )
            return ()
        return SteamApi().owned_games(
            api_key, user, use_cache=not (refresh or force_store_refresh)
        ) or ()

    # La ruta de Heroic se busca una sola vez y la comparten GOG/Epic/Amazon.
    heroic_path: Path | None = None
    heroic_path_resolved = False

    def heroic_items(store: str) -> Sequence[dict]:
        nonlocal heroic_path, heroic_path_resolved
        if not heroic_loader:
            logger.warning(
                f"{store.upper()} está activa pero la carga se ha montado sin "
                "lector de Heroic: no se cargará ninguno de sus juegos"
            )
            return ()

        if not heroic_path_resolved:
            heroic_path = heroic_loader.find_heroic_path(config.heroic_path or None)
            heroic_path_resolved = True

        if not heroic_path:
            # El porqué ya lo ha registrado `find_heroic_path`, con las rutas
            # en las que ha buscado.
            logger.warning(
                f"{store.upper()} está activa pero no hay carpeta de Heroic: "
                "no se cargará ninguno de sus juegos"
            )
            return ()

        getter = {
            "gog": heroic_loader.get_gog_games,
            "epic": heroic_loader.get_epic_games,
            "amazon": heroic_loader.get_amazon_games,
        }[store]
        return getter(heroic_path) or ()

    # (clave de config, etiqueta, clase de resolver, obtención de los crudos)
    sources = (
        ("steam", "Steam", SteamIGDBResolver, steam_items),
        ("gog", "GOG", GOGHeroicResolver, lambda: heroic_items("gog")),
        ("epic", "Epic", EpicHeroicResolver, lambda: heroic_items("epic")),
        ("amazon", "Amazon", AmazonHeroicResolver, lambda: heroic_items("amazon")),
    )

    if not stores:
        logger.warning(
            "no hay ninguna tienda activa: no hay nada que cargar "
            "(Opciones → Configuración)"
        )

    total_emitidos = 0

    try:
        for key, label, resolver_cls, get_items in sources:
            if key not in stores:
                logger.debug(f"{label} desactivada; se salta")
                continue
            try:
                raw_items = get_items()
                if not raw_items:
                    continue
                resolver = resolver_cls(igdb=engine, cache_file=CACHE_RESOLVERS)
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
