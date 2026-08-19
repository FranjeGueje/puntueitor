import base64
import hashlib
import logging
import os
import uuid
from urllib.parse import urlencode

from puntueitor.core.auth.errors import AuthError
from puntueitor.core.auth.oauth import OAuthSession
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)

AMAZON_API = "https://api.amazon.com"
REGISTER_URL = f"{AMAZON_API}/auth/register"
TOKEN_URL = f"{AMAZON_API}/auth/token"
SIGNIN_URL = "https://amazon.com/ap/signin"

#: El tipo de dispositivo del launcher de Amazon Games. Va dentro del
#: `client_id` y en el registro: si no cuadran, Amazon rechaza el alta.
DEVICE_TYPE = "A2UMVHOX7UP4V7"
APP_NAME = "AGSLauncher for Windows"
APP_VERSION = "1.0.0"
SOFTWARE_VERSION = "130050002"

#: Amazon distingue al launcher por aquí; el suyo es de Windows.
USER_AGENT = "com.amazon.agslauncher.win/3.0.9202.1"


def _b64url(datos: bytes) -> str:
    """Base64 de URL sin relleno, que es lo que pide PKCE."""
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


class AmazonSession(OAuthSession):
    """
    La sesión de Amazon Games, por "Login with Amazon" con PKCE.

    Es la más rara de las cuatro y la que más se puede romper: Amazon no
    entrega un token a una aplicación, REGISTRA UN DISPOSITIVO. Por eso hay
    un número de serie inventado que hay que conservar —el mismo que se
    registró es el que luego firma las peticiones de la biblioteca—, y por
    eso el `refresh` va contra `auth/token` con `source_token` en vez del
    `refresh_token` de toda la vida.

    El `code_verifier` de PKCE y el serial se guardan en cuanto se abre el
    navegador, no al volver: entre lo uno y lo otro el usuario puede tardar
    minutos y cerrar la aplicación, y perder el verifier a medias significa
    empezar el login de cero sin saber por qué.
    """

    STORE = str(Stores.AMAZON)
    LABEL = "Amazon"
    CODE_PARAMS = ("openid.oa2.authorization_code", "authorization_code", "code")

    def login_url(self) -> str:
        verifier = _b64url(os.urandom(32))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        serial = uuid.uuid1().hex.upper()
        client_id = (f"{serial}#{DEVICE_TYPE}").encode().hex()

        # Se guarda ANTES de mandar a nadie al navegador.
        self.tokens.save({
            **self.tokens.data,
            "device_serial": serial,
            "client_id": client_id,
            "code_verifier": verifier,
        })

        return SIGNIN_URL + "?" + urlencode({
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.mode": "checkid_setup",
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.ns.oa2": "http://www.amazon.com/ap/ext/oauth/2",
            "openid.oa2.client_id": f"device:{client_id}",
            "openid.oa2.code_challenge": challenge,
            "openid.oa2.code_challenge_method": "S256",
            "openid.oa2.scope": "device_auth_access",
            "openid.oa2.response_type": "code",
            "openid.ns.pape": "http://specs.openid.net/extensions/pape/1.0",
            "openid.pape.max_auth_age": 0,
            "openid.assoc_handle": "amzn_sonic_games_launcher",
            "openid.return_to": "https://www.amazon.com",
            "language": "es_ES",
            "pageId": "amzn_sonic_games_launcher",
        })

    @property
    def device_serial(self) -> str:
        """
        El serial con el que se registró este "dispositivo".

        Lo necesita la biblioteca para firmar sus peticiones, así que sale de
        aquí y no se regenera: uno nuevo sería otro dispositivo, y Amazon no
        lo conoce.
        """
        return self.tokens.data.get("device_serial") or ""

    def _exchange(self, code: str) -> dict:
        datos = self.tokens.data
        verifier = datos.get("code_verifier")
        client_id = datos.get("client_id")
        serial = datos.get("device_serial")
        if not (verifier and client_id and serial):
            raise AuthError(
                "el inicio de sesión de Amazon se ha perdido a medias: "
                "vuelve a empezarlo desde Opciones → Cuentas"
            )

        respuesta = self._request("POST", REGISTER_URL, json={
            "auth_data": {
                "authorization_code": code,
                "client_domain": "DeviceLegacy",
                "client_id": client_id,
                "code_algorithm": "SHA-256",
                "code_verifier": verifier,
                "use_global_authentication": False,
            },
            "registration_data": {
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "device_model": "Windows",
                "device_name": None,
                "device_serial": serial,
                "device_type": DEVICE_TYPE,
                "domain": "Device",
                "os_version": "10.0.19044.0",
                "software_version": SOFTWARE_VERSION,
            },
            "requested_extensions": ["customer_info", "device_info"],
            "requested_token_type": ["bearer"],
            "user_context_map": {"frc": ""},
        }, headers={"User-Agent": USER_AGENT})

        return self._desde_registro(respuesta, serial)

    def _desde_registro(self, respuesta: dict, serial: str) -> dict:
        """Saca el token de la respuesta de registro, que va muy anidada."""
        bearer = (
            respuesta.get("response", {})
            .get("success", {})
            .get("tokens", {})
            .get("bearer", {})
        )
        if not bearer.get("access_token"):
            raise AuthError(
                "Amazon aceptó el código pero no devolvió ninguna sesión; "
                "vuelve a intentarlo"
            )

        return {
            **self.tokens.data,
            "access_token": bearer["access_token"],
            "refresh_token": bearer.get("refresh_token", ""),
            "expires_in": bearer.get("expires_in", 3600),
            "device_serial": serial,
            # Ya no hace falta y es lo más sensible que había aquí.
            "code_verifier": "",
        }

    def _renew(self, refresh_token: str) -> dict:
        respuesta = self._request("POST", TOKEN_URL, json={
            "source_token": refresh_token,
            "source_token_type": "refresh_token",
            "requested_token_type": "access_token",
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
        }, headers={"User-Agent": USER_AGENT})

        return {
            **self.tokens.data,
            "access_token": respuesta.get("access_token", ""),
            # Amazon no manda uno nuevo al renovar: el que hay sigue valiendo
            # y borrarlo aquí cerraría la sesión en la siguiente renovación.
            "refresh_token": refresh_token,
            "expires_in": respuesta.get("expires_in", 3600),
        }
