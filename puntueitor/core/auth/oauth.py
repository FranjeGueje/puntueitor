import logging
from abc import ABC, abstractmethod

import requests

from puntueitor.core.auth.errors import AuthError, NotLoggedIn, SessionExpired
from puntueitor.core.auth.paste import extract_code
from puntueitor.core.auth.token_store import TokenStore

logger = logging.getLogger(__name__)

TIMEOUT = 20


class OAuthSession(ABC):
    """
    La sesión de una tienda: iniciarla, renovarla y dar un token válido.

    El flujo es el mismo en GOG, Epic y Amazon —abrir el navegador, pegar lo
    que devuelve, canjearlo por un token, renovarlo mientras dure—, así que
    vive aquí una sola vez. Cada tienda pone sus URLs y cómo se llaman sus
    parámetros.

    No se guarda ningún secreto de usuario más allá del token, y NADA de
    esto se registra en el log: `_post` nunca vuelca lo que envía.
    """

    #: Tienda a la que pertenece esta sesión.
    STORE: str

    #: Cómo se le llama al usuario.
    LABEL: str

    #: Nombres con los que la tienda devuelve su código, por preferencia.
    CODE_PARAMS: tuple[str, ...] = ("code",)

    def __init__(self, tokens: TokenStore | None = None, session=None):
        self.tokens = tokens or TokenStore(self.STORE)
        self._http = session or requests.Session()

    # ──────────────────────────────
    # Lo que aporta cada tienda
    # ──────────────────────────────

    @abstractmethod
    def login_url(self) -> str:
        """La página que hay que abrir en el navegador para iniciar sesión."""

    @abstractmethod
    def _exchange(self, code: str) -> dict:
        """Canjea el código recién pegado por un token."""

    @abstractmethod
    def _renew(self, refresh_token: str) -> dict:
        """Pide un token nuevo con el `refresh_token` que ya teníamos."""

    # ──────────────────────────────
    # Flujo
    # ──────────────────────────────

    def is_logged_in(self) -> bool:
        return self.tokens.has_session()

    def complete_login(self, pegado: str) -> None:
        """
        Termina el login con lo que el usuario ha pegado.

        Acepta la URL entera, el JSON de la página de redirección o el código
        a secas — ver `auth/paste.py`.
        """
        code = extract_code(pegado, self.CODE_PARAMS)
        if not code:
            raise AuthError(
                f"no se reconoce ningún código de {self.LABEL} en lo que has "
                "pegado. Copia la barra de direcciones ENTERA de la página a "
                "la que te lleva el navegador al terminar de entrar"
            )

        payload = self._exchange(code)
        self.tokens.save(payload)
        logger.info(f"{self.LABEL}: sesión iniciada")

    def logout(self) -> None:
        self.tokens.clear()
        logger.info(f"{self.LABEL}: sesión cerrada")

    def access_token(self) -> str:
        """
        Un token que sirve ahora mismo, renovándolo si hacía falta.

        Lanza `NotLoggedIn` si nunca se inició sesión y `SessionExpired` si
        la había pero ya no se puede renovar. Los proveedores distinguen los
        dos casos porque al usuario se le dice algo distinto en cada uno.
        """
        if not self.tokens.has_session():
            raise NotLoggedIn(
                f"no has iniciado sesión en {self.LABEL} (Opciones → Cuentas)"
            )

        if not self.tokens.is_expired():
            return self.tokens.access_token

        refresh_token = self.tokens.refresh_token
        if not refresh_token:
            raise SessionExpired(
                f"tu sesión de {self.LABEL} ha caducado: vuelve a entrar "
                "(Opciones → Cuentas)"
            )

        logger.debug(f"{self.LABEL}: renovando el token")
        try:
            payload = self._renew(refresh_token)
        except AuthError:
            raise
        except Exception as error:
            # Un fallo de RED renovando no es una sesión caducada: la sesión
            # probablemente siga bien y lo que falla es la conexión. Si se
            # borrara el token aquí, un rato sin internet obligaría a iniciar
            # sesión otra vez en las tres tiendas.
            raise AuthError(
                f"no se pudo renovar la sesión de {self.LABEL}: {error}"
            ) from error

        self.tokens.save(payload)
        return self.tokens.access_token

    def bearer_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token()}"}

    # ──────────────────────────────
    # HTTP
    # ──────────────────────────────

    def _post(self, url: str, data: dict) -> dict:
        """
        POST al servidor de tokens.

        Ni `data` ni la respuesta se registran nunca: ahí van el código, el
        secreto del cliente y el token.
        """
        return self._request("POST", url, data=data)

    def _get_json(self, url: str, **kwargs) -> dict:
        return self._request("GET", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            respuesta = self._http.request(
                method, url, timeout=TIMEOUT, **kwargs,
            )
        except requests.RequestException as error:
            raise AuthError(f"{self.LABEL}: {error}") from error

        if respuesta.status_code in (400, 401, 403):
            # La tienda dice que el código o el token no valen. No es un
            # problema de red: hay que volver a iniciar sesión.
            raise SessionExpired(
                f"{self.LABEL} rechazó la sesión [HTTP {respuesta.status_code}]: "
                "vuelve a iniciar sesión (Opciones → Cuentas)"
            )

        try:
            respuesta.raise_for_status()
            return respuesta.json()
        except ValueError as error:
            raise AuthError(
                f"{self.LABEL} contestó algo que no es JSON"
            ) from error
        except requests.HTTPError as error:
            raise AuthError(f"{self.LABEL}: {error}") from error
