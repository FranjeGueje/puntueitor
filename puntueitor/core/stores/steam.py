"""Steam: la única de las cuatro con API pública, y sin sesión que iniciar."""
from puntueitor.core.models import Stores
from puntueitor.core.stores.spec import StoreSpec


def _provider(config):
    from puntueitor.core.providers.steam import SteamProvider

    return SteamProvider(
        api_key=config.steam_api_key, user_id=config.steam_user_id,
    )


def _resolver():
    from puntueitor.core.resolvers.steam_resolver import SteamIGDBResolver

    return SteamIGDBResolver


SPEC = StoreSpec(
    store=Stores.STEAM,
    label="Steam",
    config_flag="steam_is_active",
    color=(0.16, 0.22, 0.34),
    provider=_provider,
    resolver=_resolver,
    # Sin sesión A PROPÓSITO: Steam no ofrece OAuth a terceros. Su OpenID
    # solo diría quién eres, sin entregar ningún permiso, así que la API key
    # haría falta igual. Ver `core/services/accounts.py`.
    session=None,
)
