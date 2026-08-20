"""
Los juegos "desconocidos" (`unknown_games`) y cómo rescatarlos.

Un desconocido es un juego que está en tu cuenta de una tienda pero que no se
pudo casar con ninguna ficha de IGDB, así que no entra en la biblioteca. Se
apunta para no volver a buscarlo en cada escaneo (ver `BaseResolver.resolve`,
que corta en seco si el juego ya está marcado) y para que puedas identificarlo
tú a mano, que es lo que hacen las funciones de aquí.

Aparte de `game_actions.py` a propósito: aquello son acciones sobre un juego
que YA está en la biblioteca, esto es el camino inverso —meter algo en ella— y
arrastra IGDB y los resolvers de cada tienda.

Mismo contrato que su hermano: nada de Textual ni de Panda3D, los imports de
red van dentro de las funciones, y **ninguna lanza**. Los frontends las llaman
desde un hilo (la búsqueda tarda segundos), y allí una excepción se pierde sin
dejar rastro.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from puntueitor.core.models import Game, Stores
from puntueitor.core.repository.library_repository import LibraryRepository

logger = logging.getLogger(__name__)

#: Cuántos resultados de IGDB se piden al buscar por título. El mismo número
#: que la TUI: suficientes para encontrar la edición correcta de un juego con
#: muchas reediciones, y caben en un menú del carrusel sin desplazarlo.
SEARCH_LIMIT = 15

def _resolvable_stores() -> tuple[str, ...]:
    """
    Las tiendas que se pueden volver a resolver por su id.

    Lo declara cada tienda en su módulo del registro, no una lista de aquí:
    era una tabla paralela más de las que había que acordarse de mantener.
    """
    from puntueitor.core import stores

    return stores.resolvable_by_id()


@dataclass(frozen=True)
class Unknown:
    """
    Una fila de `unknown_games`.

    La identidad es la pareja `(store, id)`, no el título: el mismo juego
    puede estar sin identificar en dos tiendas a la vez, y son dos entradas
    distintas que se resuelven por separado.
    """

    store: str
    title: str
    id: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.store, self.id)

    @classmethod
    def from_row(cls, row: dict) -> "Unknown":
        return cls(store=row["store"], title=row["title"], id=row["id"])


@dataclass(frozen=True)
class SearchResult:
    """Un resultado de IGDB, listo para enseñar y para adoptar."""

    igdb_id: int
    title: str
    year: int | None

    #: La ficha cruda tal cual la devolvió IGDB. Se conserva entera porque es
    #: lo que consume `IGMapperGame.map_to_game` al adoptar: volver a pedirla
    #: sería otro viaje a la red para algo que ya está en la mano.
    raw: dict

    @classmethod
    def from_raw(cls, raw: dict) -> "SearchResult":
        return cls(
            igdb_id=raw["id"],
            title=raw.get("name") or "",
            year=_release_year(raw),
            raw=raw,
        )


@dataclass(frozen=True)
class AdoptResult:
    """
    Cómo acabó el intento de identificar un desconocido.

    `unsupported` se distingue de un error normal porque no es un fallo: esa
    tienda simplemente no tiene resolver propio, y lo que hay que decirle al
    usuario es que busque por título, no que algo ha ido mal.
    """

    unknown: Unknown
    game: Game | None = None
    error: Exception | None = None
    unsupported: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and self.game is not None


def _release_year(raw: dict) -> int | None:
    """El año de salida, si viene. Es decorativo: nunca hace fallar nada."""
    timestamp = raw.get("first_release_date")
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).year
    except (OSError, ValueError, OverflowError):
        return None


def list_unknowns(repo: LibraryRepository) -> list[Unknown]:
    """
    Los desconocidos, ordenados por título.

    La tabla no tiene ORDER BY y sale en orden de inserción, que es el del
    escaneo: útil para nada. Se ordena aquí y no en cada frontend para que las
    dos interfaces los enseñen igual.

    Síncrono: solo SQLite.
    """
    return sorted(
        (Unknown.from_row(row) for row in repo.unknown_cacher.get_all()),
        key=lambda unknown: (unknown.title.casefold(), unknown.store),
    )


def search_igdb(
    title: str, limit: int = SEARCH_LIMIT,
) -> tuple[list[SearchResult], Exception | None]:
    """
    Busca un título en IGDB.

    BLOQUEA: hace red, con reintentos y espera creciente. Nunca lanza —
    devuelve `([], error)` si falló y `([], None)` si simplemente no hay nada,
    que son dos cosas distintas que contar al usuario.

    De paso, la propia búsqueda deja las fichas en la caché de IGDB
    (`cache_results` está a True por defecto), así que adoptar después no
    vuelve a pedir nada.
    """
    try:
        from puntueitor.core.igdb.service import IGDBService

        raw_results = IGDBService().search_by_title(title, limit=limit)
    except Exception as error:  # noqa: BLE001 - se reporta tal cual al llamante
        logger.warning(f"error buscando {title!r} en IGDB: {error}")
        return [], error

    results = [SearchResult.from_raw(raw) for raw in raw_results if "id" in raw]
    logger.info(f"IGDB: {len(results)} resultados para {title!r}")
    return results, None


def _enrich_new_game(repo: LibraryRepository, game: Game) -> Game:
    """
    Rellena duración y notas de un juego recién adoptado.

    Sin `overwrite`, al revés que `game_actions.enrich_game`: aquello se pide
    a mano sobre un juego concreto y rehace la búsqueda, esto es el remate
    automático de haberlo identificado.

    Se traga sus errores a propósito: el juego ya está en la biblioteca, que
    es lo que se había pedido, y quedarse sin la duración porque HLTB no
    contesta no convierte la adopción en un fracaso.
    """
    try:
        from puntueitor.core.enrichers.factory import apply_enrichers, build_enrichers

        enriched = apply_enrichers(game, build_enrichers(repo))
        if enriched.duration_hours is not None or enriched.steamdb_score is not None:
            repo.save_game(enriched)
            return enriched
    except Exception as error:  # noqa: BLE001 - la adopción ya ha salido bien
        logger.warning(f"no se pudo enriquecer el recién añadido {game.title!r}: {error}")
    return game


def adopt_result(
    repo: LibraryRepository, unknown: Unknown, result: SearchResult,
) -> AdoptResult:
    """
    Ata el desconocido a la ficha de IGDB elegida: pasa a estar en la
    biblioteca.

    El orden importa: primero se escribe la relación en `resolvers` (la fuente
    de verdad de qué está en la biblioteca) y solo entonces se quita de
    desconocidos. Al revés, un fallo en medio dejaría el juego fuera de las
    dos listas, invisible hasta el siguiente escaneo completo.

    BLOQUEA: enriquece al final. Nunca lanza.
    """
    try:
        repo.resolvers_cacher.set_igdb_ids(
            unknown.store, unknown.id, [result.igdb_id],
        )
        repo.unknown_cacher.remove_unknown(unknown.store, unknown.id)

        from puntueitor.core.mappers import IGMapperGame

        game = IGMapperGame.map_to_game(result.raw)
        game.set_store(Stores(unknown.store), unknown.id)
    except Exception as error:  # noqa: BLE001
        logger.warning(f"error adoptando {unknown.title!r}: {error}")
        return AdoptResult(unknown=unknown, error=error)

    logger.info(f"adoptado {game.title!r} ({unknown.store}) como IGDB {result.igdb_id}")
    return AdoptResult(unknown=unknown, game=_enrich_new_game(repo, game))


def resolve_by_store(repo: LibraryRepository, unknown: Unknown) -> AdoptResult:
    """
    Vuelve a intentar identificarlo con el resolver de su tienda.

    Es la vía rápida cuando el juego falló por una caída de IGDB o por un
    nombre que desde entonces se ha corregido: no hay que teclear nada.

    Hay que QUITARLO de desconocidos antes de resolver, porque el resolver se
    salta lo que ya está marcado (`BaseResolver.resolve`) y devolvería vacío
    sin intentarlo siquiera. Como consecuencia, TODOS los caminos de fallo
    tienen que volver a apuntarlo: si no, un juego que no se encuentra
    desaparecería de las dos listas y no habría forma de volver a él.

    BLOQUEA: red. Nunca lanza.
    """
    if unknown.store not in _resolvable_stores():
        # Ni se toca la tabla: no hay nada que intentar.
        logger.info(f"{unknown.store}: sin resolver propio para {unknown.title!r}")
        return AdoptResult(unknown=unknown, unsupported=True)

    repo.unknown_cacher.remove_unknown(unknown.store, unknown.id)
    try:
        games = _store_resolve(repo, unknown)
    except Exception as error:  # noqa: BLE001
        repo.unknown_cacher.save_unknown(unknown.store, unknown.title, unknown.id)
        logger.warning(f"error resolviendo {unknown.title!r} en {unknown.store}: {error}")
        return AdoptResult(unknown=unknown, error=error)

    if not games:
        repo.unknown_cacher.save_unknown(unknown.store, unknown.title, unknown.id)
        logger.info(f"{unknown.store}: sigue sin encontrarse {unknown.title!r}")
        return AdoptResult(unknown=unknown)

    logger.info(f"resuelto {games[0].title!r} desde {unknown.store}")
    return AdoptResult(unknown=unknown, game=_enrich_new_game(repo, games[0]))


def _store_resolve(repo: LibraryRepository, unknown: Unknown) -> list[Game]:
    """
    Lanza el resolver de la tienda con una ficha mínima inventada.

    Los resolvers esperan el crudo que devuelve cada tienda, del que solo
    necesitan el id y el título; aquí no se tiene ese crudo (el juego se
    escaneó hace tiempo), así que se reconstruye con lo poco que guarda
    `unknown_games`, que es justo lo que miran.

    Va con `refresh=True` para saltarse la caché de resolvers: si se está
    reintentando es porque lo cacheado no sirve.
    """
    from puntueitor.core import stores
    from puntueitor.core.igdb.service import IGDBService

    spec = stores.find(unknown.store)
    if spec is None:
        raise ValueError(f"tienda desconocida: {unknown.store}")

    igdb = IGDBService()
    resolver = spec.resolver()(igdb, repo.cache_dir / "puntueitor.db")
    raw = {spec.raw_id_field: unknown.id, "title": unknown.title}

    return list(resolver.resolve(raw, refresh=True))
