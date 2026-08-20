import logging
from urllib.parse import urlencode

from puntueitor.core.auth.oauth import OAuthSession
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)

#: A diferencia de GOG, Epic y Amazon —donde se reutiliza el `client_id`
#: público del cliente oficial de esa tienda, conocido por ingeniería
#: inversa—, itch.io no tiene ningún cliente ajeno que reutilizar: CADA
#: aplicación registra la suya en itch.io/user/settings/oauth-apps. Por eso
#: no hay una constante aquí: `client_id` llega desde `Config`
#: (`itchio_client_id`), como el de IGDB.
#:
#: Al registrar la app, el `redirect_uri` que hay que darle a itch.io es
#: `REDIRECT_URI` de aquí abajo — cualquier página fija sirve, porque no se
#: captura la redirección: el usuario copia la URL a mano, igual que con las
#: otras tres tiendas.

#: itch.io SÍ admite un `redirect_uri` a `localhost` (a diferencia de GOG,
#: Epic y Amazon, cuyo `redirect_uri` está fijado a un dominio suyo). Se usa
#: de todas formas el modo de pegar la URL, por uniformidad: un solo gesto
#: que aprender en las cuatro tiendas, en vez de que itch.io sea la única
#: que se comporta distinto. El día que eso deje de compensar, basta con
#: registrar un `redirect_uri` de loopback y cambiar solo este módulo.
REDIRECT_URI = "https://itch.io/"

AUTH_URL = "https://itch.io/user/oauth"

#: La biblioteca, y también con lo que se comprueba que un token sirve. Vive
#: aquí y no en el proveedor porque el proveedor ya importa de este módulo:
#: al revés haría falta un import diferido para no montar un ciclo.
OWNED_KEYS_URL = "https://api.itch.io/profile/owned-keys"

#: Cuánto se considera válido un token antes de revalidarlo. itch.io no hace caducar sus tokens (son claves API
#: persistentes), así que este número no protege de una caducidad real —
#: protege de tener una sesión revocada por el usuario sin que Puntueitor se
#: entere hasta la siguiente vez que intente usarla.
_VENTANA_REVALIDACION = 30 * 24 * 3600  # 30 días


class ItchioSession(OAuthSession):
    """
    La sesión de itch.io, por su OAuth2 con concesión implícita.

    Es la más distinta de las cuatro, y por un motivo estructural: itch.io no
    usa el flujo "código de autorización + canje + refresco" que sí tienen
    GOG, Epic y Amazon. Es *implicit grant*: el navegador vuelve con el
    **token ya dentro de la URL** (en el fragmento, `#access_token=...`), sin
    ningún `code` que cambiar por él, y ese token **no caduca ni tiene
    `refresh_token`**.

    `OAuthSession.access_token()` asume lo contrario: dando por caducado
    cualquier token sin `expires_at`, y exigiendo un `refresh_token` para
    poder renovarlo — con un token de itch.io tal cual, la sesión se
    invalidaría en la primera llamada después de guardarla.

    La solución se queda dentro de este módulo, sin tocar la clase
    compartida (mismo criterio que ya sigue Amazon con su registro de
    dispositivo): el propio token se guarda TAMBIÉN como si fuera su
    `refresh_token`, con una caducidad sintética de 30 días. Eso hace que,
    pasados esos 30 días, `_renew` se llame — y en vez de canjear nada,
    revalida el mismo token pidiendo la primera página de la biblioteca y lo
    vuelve a guardar. Si el usuario lo revocó desde itch.io, esa llamada
    devuelve 403 y `_request` ya lo convierte en `SessionExpired` sin más
    código aquí.
    """

    STORE = str(Stores.ITCHIO)
    LABEL = "itch.io"
    CODE_PARAMS = ("access_token",)

    def __init__(self, client_id: str = "", **kwargs):
        super().__init__(**kwargs)
        self.client_id = client_id

    def login_url(self) -> str:
        if not self.client_id:
            from puntueitor.core.auth.errors import AuthError

            raise AuthError(
                "falta el Client ID de itch.io (Opciones → Cuentas). "
                "Regístralo en itch.io/user/settings/oauth-apps"
            )
        return AUTH_URL + "?" + urlencode({
            "client_id": self.client_id,
            "scope": "profile:owned",
            "redirect_uri": REDIRECT_URI,
            "response_type": "token",
        })

    def _exchange(self, code: str) -> dict:
        # No hay nada que "canjear": `code` YA ES el access_token, sacado del
        # fragmento de la URL pegada. Se comprueba antes de darlo por bueno,
        # para no guardar un token roto o sin el scope `profile:owned` sin
        # que se note hasta la primera recarga.
        self._verificar(code)
        return self._payload(code)

    def _renew(self, refresh_token: str) -> dict:
        # `refresh_token` es el mismo access_token, guardado por partida
        # doble (ver la clase). No hay canje real: solo revalidar.
        self._verificar(refresh_token)
        return self._payload(refresh_token)

    def _verificar(self, token: str) -> None:
        """
        Que el token sirve, preguntándoselo a itch.io.

        Se comprueba contra la BIBLIOTECA y no contra `/profile`, que sería
        más ligero, porque `/profile` exige el permiso `profile:me` y aquí
        solo se pide `profile:owned`: contesta 403 aunque el token sea
        perfectamente válido, y el login no funcionaba nunca. Además así se
        prueba justo lo que hace falta que funcione, en vez de algo parecido.
        """
        self._get_json(
            OWNED_KEYS_URL,
            params={"page": 1},
            headers={"Authorization": f"Bearer {token}"},
        )

    @staticmethod
    def _payload(token: str) -> dict:
        return {
            "access_token": token,
            "refresh_token": token,
            "expires_in": _VENTANA_REVALIDACION,
        }
