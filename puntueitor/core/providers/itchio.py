import logging
from collections.abc import Sequence

from puntueitor.core.auth.itchio import OWNED_KEYS_URL, ItchioSession
from puntueitor.core.models import Stores
from puntueitor.core.providers.base import LibraryProvider

logger = logging.getLogger(__name__)

#: itch.io no dice cuántas páginas hay —a diferencia de GOG—, así que se
#: para sola cuando llega una página vacía. El tope es la red de seguridad
#: por si algún día contestara mal y no dejara de haber páginas nunca.
POR_PAGINA = 50
MAX_PAGINAS = 200

TIMEOUT = 20


class ItchioProvider(LibraryProvider):
    """
    La biblioteca de itch.io, por su "Owned Keys API Route" oficial.

    A diferencia de GOG/Epic/Amazon, esta SÍ es una API pública y documentada
    por el propio itch.io (itch.io/docs/api/oauth), con el scope
    `profile:owned`. No hay nada que averiguar por ingeniería inversa aquí.
    """

    STORE = Stores.ITCHIO
    LABEL = "itch.io"

    def __init__(self, session: ItchioSession | None = None, cacher=None, http=None):
        super().__init__(cacher)
        self.session = session or ItchioSession()
        self._http = http

    def is_ready(self) -> tuple[bool, str]:
        if not self.session.is_logged_in():
            return False, "no has iniciado sesión en itch.io (Opciones → Cuentas)"
        return True, ""

    def _fetch_remote(self) -> Sequence[dict]:
        headers = self.session.bearer_headers()

        juegos: list[dict] = []
        for pagina in range(1, MAX_PAGINAS + 1):
            datos = self._get(headers, pagina)
            claves = datos.get("owned_keys") or []
            if not claves:
                break
            juegos.extend(
                self._normalizar(clave) for clave in claves
                if isinstance(clave.get("game"), dict)
            )
            if len(claves) < POR_PAGINA:
                break
        else:
            logger.warning(
                f"itch.io: se ha parado en la página {MAX_PAGINAS}; puede "
                "faltar parte de la biblioteca"
            )

        return juegos

    def _get(self, headers: dict, pagina: int) -> dict:
        import requests

        http = self._http or requests
        respuesta = http.get(
            OWNED_KEYS_URL, params={"page": pagina}, headers=headers,
            timeout=TIMEOUT,
        )
        respuesta.raise_for_status()
        return respuesta.json()

    @staticmethod
    def _normalizar(clave: dict) -> dict:
        """
        La clave con las claves (nunca mejor dicho) que espera su resolver.

        `app_name` es el mismo `game.id` numérico que IGDB indexa como `uid`
        de su fuente externa "Itchio" (comprobado contra la API real de
        IGDB): no hace falta ningún mapeo entre los dos.
        """
        juego = clave["game"]
        return {
            "app_name": str(juego.get("id") or ""),
            "title": juego.get("title") or "",
            "store_url": juego.get("url") or "",
        }

    @staticmethod
    def store_id(raw: dict) -> str:
        return str(raw.get("app_name") or "")
