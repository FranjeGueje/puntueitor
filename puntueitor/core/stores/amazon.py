"""Amazon."""
from puntueitor.core.models import Stores
from puntueitor.core.stores.spec import StoreSpec


def _provider(config):
    from puntueitor.core.providers.amazon import AmazonProvider

    return AmazonProvider()


def _resolver():
    from puntueitor.core.resolvers.amazon_resolver import AmazonResolver

    return AmazonResolver


def _session(config):
    from puntueitor.core.auth.amazon import AmazonSession

    return AmazonSession()


SPEC = StoreSpec(
    store=Stores.AMAZON,
    label="Amazon",
    config_flag="amazon_is_active",
    banner_label="AMZN",
    color=(0.82,0.53,0.13),
    provider=_provider,
    resolver=_resolver,
    session=_session,
    paste_hint="Pega la dirección a la que te lleva Amazon al entrar",
    # Amazon no expone ningún id que IGDB conozca: sus juegos se identifican
    # por título, así que volver a resolverlos "por su tienda" no significa
    # nada. Rescatarlos es buscarlos a mano.
    resolvable_by_id=False,
)
