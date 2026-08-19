import hashlib
import logging
from collections.abc import Sequence

from puntueitor.core.auth.amazon import USER_AGENT, AmazonSession
from puntueitor.core.models import Stores
from puntueitor.core.providers.base import LibraryProvider

logger = logging.getLogger(__name__)

ENTITLEMENTS_URL = "https://gaming.amazon.com/api/distribution/entitlements"

#: Los manda el launcher de Amazon tal cual; sin ellos la petición se
#: rechaza. `keyId` es una constante de su servicio, no algo nuestro.
TARGET = (
    "com.amazon.animusdistributionservice.entitlement"
    ".AnimusEntitlementsService.GetEntitlements"
)
KEY_ID = "d5dc8b8b-86c8-4fc4-ae93-18c0def5314d"

POR_PAGINA = 50
MAX_PAGINAS = 100
TIMEOUT = 20


class AmazonProvider(LibraryProvider):
    """
    La biblioteca de Amazon Games (Prime Gaming), por su servicio de
    *entitlements* — la misma que usa Nile.

    Es la más frágil de las cuatro y conviene saberlo: Amazon no documenta
    nada de esto, la petición imita al launcher de Windows campo por campo
    (cabeceras, `hardwareHash`, `clientId`) y cualquier cambio suyo la rompe.
    Por eso importa que la caché aguante: si Amazon deja de contestar, tus
    juegos siguen ahí hasta que se arregle.
    """

    STORE = Stores.AMAZON
    LABEL = "Amazon"

    def __init__(self, session: AmazonSession | None = None, cacher=None, http=None):
        super().__init__(cacher)
        self.session = session or AmazonSession()
        self._http = http

    def is_ready(self) -> tuple[bool, str]:
        if not self.session.is_logged_in():
            return False, "no has iniciado sesión en Amazon (Opciones → Cuentas)"
        if not self.session.device_serial:
            return False, (
                "la sesión de Amazon está incompleta: vuelve a iniciarla "
                "(Opciones → Cuentas)"
            )
        return True, ""

    def _fetch_remote(self) -> Sequence[dict]:
        import requests

        http = self._http or requests
        headers = {
            "X-Amz-Target": TARGET,
            "x-amzn-token": self.session.access_token(),
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Content-Encoding": "amz-1.0",
        }
        # Amazon espera el hash del serial del dispositivo registrado, no el
        # serial en claro.
        hardware_hash = hashlib.sha256(
            self.session.device_serial.encode()
        ).hexdigest().upper()

        juegos: list[dict] = []
        next_token = None
        for _ in range(MAX_PAGINAS):
            respuesta = http.post(
                ENTITLEMENTS_URL,
                headers=headers,
                json={
                    "Operation": "GetEntitlements",
                    "clientId": "Sonic",
                    "syncPoint": None,
                    "nextToken": next_token,
                    "maxResults": POR_PAGINA,
                    "productIdFilter": None,
                    "keyId": KEY_ID,
                    "hardwareHash": hardware_hash,
                },
                timeout=TIMEOUT,
            )
            respuesta.raise_for_status()
            datos = respuesta.json()

            for entitlement in datos.get("entitlements") or ():
                juego = self._normalizar(entitlement)
                if juego:
                    juegos.append(juego)

            next_token = datos.get("nextToken")
            if not next_token:
                break
        else:
            logger.warning(
                f"Amazon: se ha parado en la página {MAX_PAGINAS}; puede "
                "faltar parte de la biblioteca"
            )

        return juegos

    @staticmethod
    def _normalizar(entitlement: dict) -> dict | None:
        """
        El *entitlement* con las claves que espera su resolver.

        `extra.releaseDate` se conserva con ese nombre porque es lo que mira
        `AmazonResolver` para desempatar entre juegos del mismo título:
        Amazon no tiene ningún identificador que IGDB conozca, así que la
        fecha de salida es lo único que distingue un remaster de su original.
        """
        producto = entitlement.get("product")
        if not isinstance(producto, dict):
            return None

        product_id = producto.get("id") or producto.get("productAsin")
        title = producto.get("title") or producto.get("productTitle")
        if not product_id:
            return None

        return {
            "app_name": str(product_id),
            "title": title or "",
            "extra": {"releaseDate": producto.get("releaseDate")},
            "product": producto,
        }

    @staticmethod
    def store_id(raw: dict) -> str:
        return str(raw.get("app_name") or "")
