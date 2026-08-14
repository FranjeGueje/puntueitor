"""
Acciones sobre UN juego suelto: enriquecerlo y desconocerlo.

Aparte del pipeline (`core/pipeline/`), que trabaja siempre con la biblioteca
entera: esto es lo que se pide desde una interfaz con un juego delante, y no
tiene sentido montar un `Library` de uno para ello.

Vive aquí y no en cada frontend porque las dos interfaces —la TUI y el
carrusel 3D— ofrecen exactamente las mismas dos acciones, y estaban escritas
a mano dentro de `tui/app.py`: dos copias que se habrían separado a la
primera corrección.

Ninguna de las dos sabe nada de Textual ni de Panda3D. `enrich_game` en
concreto no notifica ni lanza: devuelve los tres desenlaces posibles en un
`EnrichResult` para que cada interfaz los traduzca a su manera de avisar.
"""
import logging
from dataclasses import dataclass

from puntueitor.core.models import Game
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.services.store_titles import store_title

logger = logging.getLogger(__name__)

#: Los campos que decide si el enriquecido ha servido de algo. Son los que
#: rellenan los dos enrichers; si ninguno llegó, no hay nada que guardar y se
#: avisa de que no se encontró el juego en vez de escribir una fila vacía.
_ENRICHED_FIELDS = ("duration_hours", "steam_review", "steamdb_score")


@dataclass(frozen=True)
class EnrichResult:
    """
    Cómo acabó un enriquecido, sin acoplarse a ninguna interfaz.

    Son tres desenlaces, no dos, y hay que poder distinguirlos: "no se
    encontró nada" es normal y se avisa de pasada, mientras que un error
    (sin red, HLTB caído) es un fallo que el usuario querrá ver.
    """

    #: El juego enriquecido, o el original si no hubo nada que añadir.
    game: Game

    #: ¿Trajo algún dato? Si es True, ya está persistido.
    found: bool

    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def enrich_game(repo: LibraryRepository, game: Game) -> EnrichResult:
    """
    Busca duración (HowLongToBeat) y notas de Steam para un solo juego.

    BLOQUEA: hace peticiones de red. Quien llama decide en qué hilo — la TUI
    usa un hilo daemon y el carrusel 3D su `EnrichWorker`.

    Nunca lanza: una excepción se devuelve dentro del resultado. Así el
    llamante no tiene que envolver la llamada en un try dentro de su hilo de
    trabajo, que es justo donde una excepción se pierde sin dejar rastro.

    Va con `overwrite=True` a propósito: se ha pedido a mano sobre este juego
    en concreto, así que rehace la búsqueda aunque ya hubiera datos o ya se
    hubiera buscado sin éxito (`extras.hltb_checked`) — al contrario que el
    pipeline, que recorre la biblioteca entera y debe saltarse lo ya hecho.
    """
    try:
        # Dentro de la función a propósito: estos módulos arrastran las
        # dependencias de red (requests, la librería de HLTB) y no deben
        # cargarse por el mero hecho de importar este fichero.
        from puntueitor.core.enrichers.hltb_enricher import HLTBEnricher
        from puntueitor.core.enrichers.steam_score_enricher import SteamScoreEnricher
        from puntueitor.core.resolvers.hltb_resolver import HLTBResolver

        hltb = HLTBEnricher(
            client=HLTBResolver(),
            overwrite=True,
            extras_cacher=repo.extras_cacher,
        )
        steam = SteamScoreEnricher(overwrite=True, igdb_cacher=repo.igdb_cacher)
        enriched = steam.enrich(hltb.enrich(game))
    except Exception as error:  # noqa: BLE001 - se reporta tal cual al llamante
        logger.warning(f"error enriqueciendo {game.title!r}: {error}")
        return EnrichResult(game=game, found=False, error=error)

    if any(getattr(enriched, field) is not None for field in _ENRICHED_FIELDS):
        repo.save_game(enriched)
        logger.info(f"enriquecido {enriched.title!r}")
        return EnrichResult(game=enriched, found=True)

    logger.info(f"sin datos para {game.title!r}")
    return EnrichResult(game=enriched, found=False)


def forget_game(repo: LibraryRepository, game: Game) -> dict[str, str]:
    """
    "Desconocer": saca el juego de la biblioteca y lo manda a desconocidos.

    Devuelve las tiendas en las que estaba (`{tienda: id}`), o `{}` si no
    estaba en ninguna.

    Lo que se borra es la relación con IGDB en `resolvers`, que según la
    "Regla de Oro" es la única fuente de verdad de qué está en la biblioteca;
    la ficha en la caché de IGDB se queda, porque es una caché global de todo
    lo consultado y no representa posesión.

    Cada id de tienda se apunta en `unknown_games` para que el siguiente
    escaneo no lo vuelva a resolver al mismo juego y puedas identificarlo tú
    a mano: por eso hay que LEER las tiendas antes de borrar la relación.

    Y se apunta con el nombre que tiene EN SU TIENDA, no con el de IGDB: se
    está desconociendo justamente porque IGDB lo identificó mal, así que
    guardar ese nombre borraría la pista de qué juego era de verdad. Es
    además lo que hace el escaneo cuando un desconocido nace por su cuenta
    (`BaseResolver.resolve`), así que las dos vías dejan la tabla igual. Si
    la tienda no se puede consultar, el de IGDB es mejor que ninguno.

    El nombre se busca por tienda, no una vez: un juego que esté en dos se
    llama distinto en cada una.

    Síncrono: solo toca ficheros locales, no hay nada que esperar.
    """
    stores = repo.resolvers_cacher.get_stores_for_igdb_id(game.igdb_id) or {}
    repo.resolvers_cacher.remove_igdb_id(game.igdb_id)
    for store_name, store_id in stores.items():
        title = store_title(store_name, str(store_id)) or game.title
        repo.unknown_cacher.save_unknown(store_name, title, str(store_id))
    logger.info(f"desconocido {game.title!r}: {sorted(stores)}")
    return stores
