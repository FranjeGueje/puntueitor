"""
La única forma de construir los enrichers.

Existe porque construirlos a mano salió caro: había seis sitios haciéndolo y
**cinco se olvidaban de pasarle a `SteamScoreEnricher` su `extras_cacher`**,
así que las notas de Steam solo se guardaban al recargar la biblioteca. En
los otros cinco caminos —enriquecer un juego suelto, rescatar un desconocido,
actualizar los extras— se volvían a pedir en cada pasada y se perdían al
cerrar.

La lección no es "acordarse del argumento". Es que **dónde guarda cada
enricher no puede ser una decisión de quien lo construye**: es del enricher, y
aquí se le da todo lo que sabe usar.
"""
import logging

logger = logging.getLogger(__name__)


def build_enrichers(repo, *, overwrite: bool = False) -> list:
    """
    Los enrichers listos para usar, con sus cachers puestos.

    `overwrite=True` los hace reescribir lo que ya hubiera —es lo que quiere
    "enriquecer DESTRUCTIVO"—; con `False` respetan lo conocido, que es lo
    normal.

    Si uno falla al prepararse se registra y se sigue con los demás. Esa
    resistencia la tenía solo `refresh_library`: los otros cinco sitios se
    habrían quedado sin enriquecer nada porque falle el que no toca.
    """
    # Dentro: arrastran red (HowLongToBeat, Steam) y este módulo lo importan
    # servicios que a veces solo quieren la lista.
    from puntueitor.core.enrichers.hltb_enricher import HLTBEnricher
    from puntueitor.core.enrichers.steam_score_enricher import SteamScoreEnricher
    from puntueitor.core.resolvers.hltb_resolver import HLTBResolver

    def _hltb():
        return HLTBEnricher(
            client=HLTBResolver(),
            overwrite=overwrite,
            extras_cacher=repo.extras_cacher,
        )

    def _steam():
        return SteamScoreEnricher(
            overwrite=overwrite,
            igdb_cacher=repo.igdb_cacher,
            # El que faltaba en cinco de los seis sitios.
            extras_cacher=repo.extras_cacher,
        )

    enrichers = []
    for nombre, construir in (("HLTB", _hltb), ("las notas de Steam", _steam)):
        try:
            enrichers.append(construir())
        except Exception as error:  # noqa: BLE001 - se sigue sin ese enricher
            logger.warning(f"no se pudo preparar {nombre}: {error}")
    return enrichers


def apply_enrichers(game, enrichers):
    """
    Pasa el juego por todos los enrichers, en orden.

    Sustituye al `steam.enrich(hltb.enrich(game))` que estaba escrito en
    cuatro sitios: con la lista de la fábrica, quien enriquece deja de tener
    que saber cuántos enrichers hay ni en qué orden van.
    """
    for enricher in enrichers:
        game = enricher.enrich(game)
    return game
