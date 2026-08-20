"""
itch.io.

La única de las cinco tiendas con API oficial y pública. También la única
que exige registrar una aplicación propia (`itch.io/user/settings/oauth-apps`):
no hay client_id ajeno que reutilizar como en GOG/Epic/Amazon, así que
`_session` recibe la configuración para leer `itchio_client_id`.
"""
from puntueitor.core.models import Stores
from puntueitor.core.stores.spec import StoreSpec


def _provider(config):
    from puntueitor.core.auth.itchio import ItchioSession
    from puntueitor.core.providers.itchio import ItchioProvider

    return ItchioProvider(
        session=ItchioSession(client_id=config.itchio_client_id),
    )


def _resolver():
    from puntueitor.core.resolvers.itchio_resolver import ItchioResolver

    return ItchioResolver


def _session(config):
    from puntueitor.core.auth.itchio import ItchioSession

    return ItchioSession(client_id=config.itchio_client_id)


SPEC = StoreSpec(
    store=Stores.ITCHIO,
    label="itch.io",
    config_flag="itchio_is_active",
    banner_label="ITCH",
    color=(0.98, 0.30, 0.30),
    provider=_provider,
    resolver=_resolver,
    session=_session,
    paste_hint="Pega la dirección a la que te lleva la página tras autorizar",
    # IGDB sí indexa itch.io como fuente externa (id 30, comprobado contra
    # la API real), así que sus juegos se pueden volver a resolver por id
    # como los de Steam o GOG.
    resolvable_by_id=True,
)
