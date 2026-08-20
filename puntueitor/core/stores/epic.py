"""Epic."""
from puntueitor.core.models import Stores
from puntueitor.core.stores.spec import StoreSpec


def _provider(config):
    from puntueitor.core.providers.epic import EpicProvider

    return EpicProvider()


def _resolver():
    from puntueitor.core.resolvers.epic_resolver import EpicResolver

    return EpicResolver


def _session(config):
    from puntueitor.core.auth.epic import EpicSession

    return EpicSession()


SPEC = StoreSpec(
    store=Stores.EPIC,
    label="Epic",
    config_flag="epic_is_active",
    color=(0.22,0.22,0.24),
    provider=_provider,
    resolver=_resolver,
    session=_session,
    paste_hint="Pega el texto que sale en la página (o su dirección)",
)
