"""
Iniciar y cerrar sesión en las tiendas, sin saber nada de interfaces.

Aquí solo están GOG, Epic y Amazon. **Steam no**, y no por olvido: Steam no
tiene OAuth para terceros. Su OpenID únicamente dice quién eres, sin entregar
ningún token, así que la biblioteca sigue necesitando la API key igual —
"conectar la cuenta de Steam" no ahorraba el paso manual, solo ahorraba
teclear diecisiete cifras, y a cambio hacía parecer que Steam se configura
como las demás cuando no es verdad. Se configura con su clave y su ID, en
`config.json`, y ya está.

El flujo de las tres que sí lo tienen es idéntico y esa uniformidad es
deliberada: se abre el navegador, el usuario entra, y pega de vuelta lo que
le salga en la barra de direcciones.

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

def con_sesion():
    """
    Las tiendas que tienen sesión que iniciar (ver arriba por qué Steam no).

    Sale del registro, y cada tienda lo declara en su propio módulo con
    `session=None` o no. Antes era una lista aparte que había que acordarse
    de mantener, y recorrer el enum entero en vez de esta lista fue
    exactamente lo que coló a Steam donde no tocaba.
    """
    from puntueitor.core import stores

    return tuple(spec.store for spec in stores.with_session())


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
    """La sesión de una tienda, del registro."""
    from puntueitor.core import stores

    spec = stores.find(store)
    if spec is None or not spec.has_session:
        raise ValueError(f"{store} no usa sesión")
    return spec.session()


def login_url(store: str) -> str:
    """La dirección que hay que abrir para entrar en `store`."""
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
        # Corto a propósito: lo que hay que pegar y dónde ya lo dice el campo
        # que sale justo después —el título del cuadro en el carrusel, el
        # marcador de posición en la terminal—, así que repetirlo aquí solo
        # llenaba de texto un aviso que se lee de pasada.
        return LoginResult(True, "Inicia sesión en el navegador abierto")

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

    """
    store = str(store)
    if not (pegado or "").strip():
        return LoginResult(False, "No has pegado nada.")

    try:
        _sesion(store).complete_login(pegado)
    except AuthError as error:
        return LoginResult(False, str(error))
    except Exception as error:  # noqa: BLE001 - cualquier cosa, pero contada
        logger.warning(f"falló el login de {store}: {error}", exc_info=True)
        return LoginResult(False, f"No se pudo iniciar sesión: {error}")

    return LoginResult(True, "Sesión iniciada. Refresca la biblioteca para "
                             "traerte tus juegos.")


def logout(store: str) -> LoginResult:
    """Cierra la sesión de una tienda."""
    store = str(store)
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
    try:
        from puntueitor.core.auth.token_store import TokenStore

        return TokenStore(store).has_session()
    except Exception as error:  # noqa: BLE001
        logger.debug(f"no se pudo mirar la sesión de {store}: {error}")
        return False


def sessions_summary() -> dict[str, bool]:
    """
    El estado de las tiendas con sesión, para pintarlo de una vez.

    Se recorre `CON_SESION` y no `Stores`: recorriendo el enum entero se
    colaba Steam, que no tiene sesión ninguna que enseñar.
    """
    return {str(store): has_session(store) for store in con_sesion()}
