import base64
import logging
from urllib.parse import urlencode

from puntueitor.core.auth.oauth import OAuthSession
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)

#: Las credenciales del Epic Games Launcher, las mismas que usa Legendary.
#: Como en GOG, no es un secreto: viene dentro del cliente oficial y Epic no
#: registra aplicaciones de terceros para esto.
CLIENT_ID = "34a02cf8f4414e29b15921876da36f9a"
CLIENT_SECRET = "daafbccc737745039dffe53d94fc76cf"

BASIC = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

#: Epic mira el User-Agent y trata distinto al que no parece su launcher.
USER_AGENT = (
    "UELauncher/11.0.1-14907503+++Portal+Release-Live "
    "Windows/10.0.19041.1.256.64bit"
)

LOGIN_URL = "https://www.epicgames.com/id/login"
REDIRECT_URL = "https://www.epicgames.com/id/api/redirect"
TOKEN_URL = (
    "https://account-public-service-prod03.ol.epicgames.com"
    "/account/api/oauth/token"
)


class EpicSession(OAuthSession):
    """
    La sesión de Epic, por el OAuth del launcher.

    El código no llega por un redirect que podamos recoger: Epic lo enseña en
    una página suya, en un JSON con la forma `{"authorizationCode": "..."}`.
    Por eso `CODE_PARAMS` acepta ese nombre y `paste.py` sabe leer un JSON
    entero — el usuario copia lo que ve y ya está.
    """

    STORE = str(Stores.EPIC)
    LABEL = "Epic"
    CODE_PARAMS = ("authorizationCode", "code")

    def login_url(self) -> str:
        # Se entra por el login y se le dice a dónde ir DESPUÉS: si el
        # usuario ya tenía sesión en el navegador, Epic salta la pantalla y
        # enseña el código directamente.
        destino = f"{REDIRECT_URL}?" + urlencode({
            "clientId": CLIENT_ID,
            "responseType": "code",
        })
        return LOGIN_URL + "?" + urlencode({"redirectUrl": destino})

    def _exchange(self, code: str) -> dict:
        return self._token_request({
            "grant_type": "authorization_code",
            "code": code,
            "token_type": "eg1",
        })

    def _renew(self, refresh_token: str) -> dict:
        return self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "token_type": "eg1",
        })

    def _token_request(self, data: dict) -> dict:
        return self._request(
            "POST", TOKEN_URL, data=data,
            headers={
                "Authorization": f"basic {BASIC}",
                "User-Agent": USER_AGENT,
            },
        )
