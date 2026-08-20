"""GOG."""
from puntueitor.core.models import Stores
from puntueitor.core.stores.spec import StoreSpec


def _provider(config):
    from puntueitor.core.providers.gog import GOGProvider

    return GOGProvider()


def _resolver():
    from puntueitor.core.resolvers.gog_resolver import GOGResolver

    return GOGResolver


def _session(config):
    from puntueitor.core.auth.gog import GOGSession

    return GOGSession()


SPEC = StoreSpec(
    store=Stores.GOG,
    label="GOG",
    config_flag="gog_is_active",
    color=(0.48,0.24,0.58),
    provider=_provider,
    resolver=_resolver,
    session=_session,
    paste_hint="Pega la dirección de la página en blanco a la que llegas",
)
