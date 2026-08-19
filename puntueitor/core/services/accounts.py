"""
Iniciar y cerrar sesión en las tiendas, sin saber nada de interfaces.

El flujo es idéntico en las cuatro y esa uniformidad es deliberada: se abre
el navegador, el usuario entra, y pega de vuelta lo que le salga en la barra
de direcciones. Steam podría recoger su respuesta en un servidor local —su
OpenID sí acepta volver a `localhost`—, pero se le pide lo mismo que a las
otras tres: un solo gesto que aprender en vez de dos.

Como el resto de `core/services`, aquí los errores SE DEVUELVEN, no se
lanzan: esto lo llama la TUI y también el carrusel, muchas veces desde un
hilo, y una excepción cruzando esa frontera es un cierre en seco.
"""
import logging
import webbrowser
from dataclasses import dataclass

from puntueitor.core.auth.errors import AuthError
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)

#: Las tiendas que necesitan iniciar sesión. Steam va aparte: no tiene
#: sesión, tiene una API key que el usuario copia de su página de Steam.
CON_SESION = (Stores.GOG, Stores.EPIC, Stores.AMAZON)


@dataclass(frozen=True)
class LoginResult:
    """Cómo ha ido, y qué contarle al usuario."""

    ok: bool
    mensaje: str

    #: La dirección de login, solo cuando el usuario tiene que abrirla él.
    #: Va aparte del mensaje porque una URL de trescientos caracteres cabe
    #: en la terminal pero no en un aviso del carrusel, y cada interfaz
    #: sabe qué hacer con ella.
    url: str = ""


def _sesion(store: str):
    """La clase de sesión de una tienda. Importa dentro: arrastra `requests`."""
    store = str(store)
    if store == Stores.GOG:
        from puntueitor.core.auth.gog import GOGSession
        return GOGSession()
    if store == Stores.EPIC:
        from puntueitor.core.auth.epic import EpicSession
        return EpicSession()
    if store == Stores.AMAZON:
        from puntueitor.core.auth.amazon import AmazonSession
        return AmazonSession()
    raise ValueError(f"{store} no usa sesión")


def login_url(store: str) -> str:
    """La dirección que hay que abrir para entrar en `store`."""
    if str(store) == Stores.STEAM:
        from puntueitor.core.auth.steam import login_url as steam_login_url
        return steam_login_url()
    return _sesion(store).login_url()


def open_login(store: str) -> LoginResult:
    """
    Abre el navegador en la página de login de la tienda.

    Si no hay navegador que abrir —una sesión por SSH, un Deck en modo
    juego— no es un fallo: se devuelve la dirección para que el usuario la
    abra donde pueda. Quedarse sin poder iniciar sesión por eso sería
    absurdo.
    """
    try:
        url = login_url(store)
    except Exception as error:  # noqa: BLE001 - se informa, no se revienta
        logger.warning(f"no se pudo preparar el login de {store}: {error}")
        return LoginResult(False, f"no se pudo preparar el inicio de sesión: {error}")

    try:
        abierto = webbrowser.open(url)
    except Exception as error:  # noqa: BLE001
        logger.debug(f"webbrowser falló: {error}")
        abierto = False

    if abierto:
        return LoginResult(True, "Se ha abierto el navegador. Cuando termines de "
                                 "entrar, pega aquí la dirección de la página.")

    # Sin navegador —por SSH, o en el modo juego del Deck— no se puede hacer
    # nada por el usuario, pero tampoco hay que dejarle tirado: la dirección
    # queda en el log, que sí puede abrir.
    logger.info(f"no se pudo abrir el navegador. Entra en {store} por: {url}")
    return LoginResult(
        True,
        "No se ha podido abrir el navegador. La dirección para entrar está "
        "en el log de esta sesión.",
        url=url,
    )


def finish_login(store: str, pegado: str) -> LoginResult:
    """
    Termina el inicio de sesión con lo que el usuario ha pegado.

    En Steam esto no guarda ningún token —no lo hay—: guarda el Steam ID en
    la configuración, que es lo que hasta ahora había que teclear a mano.
    """
    store = str(store)
    if not (pegado or "").strip():
        return LoginResult(False, "No has pegado nada.")

    if store == Stores.STEAM:
        return _finish_steam(pegado)

    try:
        _sesion(store).complete_login(pegado)
    except AuthError as error:
        return LoginResult(False, str(error))
    except Exception as error:  # noqa: BLE001 - cualquier cosa, pero contada
        logger.warning(f"falló el login de {store}: {error}", exc_info=True)
        return LoginResult(False, f"No se pudo iniciar sesión: {error}")

    return LoginResult(True, "Sesión iniciada. Refresca la biblioteca para "
                             "traerte tus juegos.")


def _finish_steam(pegado: str) -> LoginResult:
    from puntueitor.core.auth.steam import steam_id_from
    from puntueitor.core.config import ConfigManager

    steam_id = steam_id_from(pegado)
    if not steam_id:
        return LoginResult(False, (
            "Ahí no hay ningún Steam ID de 17 cifras. Pega la dirección "
            "entera a la que te lleva Steam al terminar de entrar."
        ))

    manager = ConfigManager()
    manager.get.steam_user_id = int(steam_id)
    manager.save()
    return LoginResult(True, f"Steam ID {steam_id} guardado.")


def logout(store: str) -> LoginResult:
    """Cierra la sesión de una tienda."""
    store = str(store)
    if store == Stores.STEAM:
        from puntueitor.core.config import ConfigManager

        manager = ConfigManager()
        manager.get.steam_user_id = 0
        manager.save()
        return LoginResult(True, "Steam ID borrado.")

    try:
        _sesion(store).logout()
    except Exception as error:  # noqa: BLE001
        logger.warning(f"no se pudo cerrar la sesión de {store}: {error}")
        return LoginResult(False, f"No se pudo cerrar la sesión: {error}")

    return LoginResult(True, "Sesión cerrada.")


def has_session(store: str) -> bool:
    """
    Si hay sesión guardada en `store`.

    No se comprueba si SIGUE valiendo: eso son tres peticiones de red, y esto
    lo llama la interfaz para pintar una lista.
    """
    store = str(store)
    if store == Stores.STEAM:
        from puntueitor.core.config import ConfigManager

        config = ConfigManager().get
        return bool(config.steam_api_key and config.steam_user_id)

    try:
        from puntueitor.core.auth.token_store import TokenStore

        return TokenStore(store).has_session()
    except Exception as error:  # noqa: BLE001
        logger.debug(f"no se pudo mirar la sesión de {store}: {error}")
        return False


def sessions_summary() -> dict[str, bool]:
    """El estado de las cuatro tiendas, para pintarlo de una vez."""
    return {str(store): has_session(store) for store in Stores}
