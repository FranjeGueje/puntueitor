import logging
from urllib.parse import urlencode

from puntueitor.core.auth.oauth import OAuthSession
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)

#: Las credenciales del cliente oficial de GOG (Galaxy), las mismas que usan
#: gogdl y Heroic. No son un secreto nuestro ni del usuario: van dentro de un
#: programa que cualquiera puede descargar, y GOG no ofrece registro de
#: aplicaciones de terceros. Es la única puerta que hay.
CLIENT_ID = "46899977096215655"
CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"

#: Fijado por GOG, no elegible por nosotros: por eso el usuario tiene que
#: pegar la URL a mano en vez de volver a un `localhost` nuestro.
REDIRECT_URI = "https://embed.gog.com/on_login_success?origin=client"

AUTH_URL = "https://auth.gog.com/auth"
TOKEN_URL = "https://auth.gog.com/token"


class GOGSession(OAuthSession):
    """La sesión de GOG, por el OAuth2 de `auth.gog.com`."""

    STORE = str(Stores.GOG)
    LABEL = "GOG"
    CODE_PARAMS = ("code",)

    def login_url(self) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "layout": "client2",
        })

    def _exchange(self, code: str) -> dict:
        # GET y no POST: es lo que espera `auth.gog.com` y lo que hace el
        # propio gogdl. Por eso los datos van como `params`.
        return self._token_request({
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        })

    def _renew(self, refresh_token: str) -> dict:
        return self._token_request({
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        })

    def _token_request(self, params: dict) -> dict:
        return self._get_json(TOKEN_URL, params=params)
