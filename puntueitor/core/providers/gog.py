import logging
from collections.abc import Sequence

from puntueitor.core.auth.gog import GOGSession
from puntueitor.core.models import Stores
from puntueitor.core.providers.base import LibraryProvider

logger = logging.getLogger(__name__)

PRODUCTS_URL = "https://embed.gog.com/account/getFilteredProducts"

#: Tope de páginas. GOG dice cuántas hay y el bucle para solo; esto es la red
#: por si algún día contesta mal y `totalPages` no baja nunca. Con 50 juegos
#: por página son 5.000, muy por encima de cualquier biblioteca real.
MAX_PAGINAS = 100

TIMEOUT = 20


class GOGProvider(LibraryProvider):
    """
    La biblioteca de GOG, por la misma API que usa GOG Galaxy.

    No es una API pública documentada por GOG, pero es la del cliente
    oficial: la que hay debajo de gogdl y, por tanto, de lo que Heroic
    escribía en `gog_library.json`. La diferencia es que ahora la sesión es
    nuestra y no hace falta que Heroic exista.

    Se pide `getFilteredProducts` y no `/user/data/games` porque el segundo
    solo devuelve identificadores, y entonces harían falta cientos de
    peticiones más para saber cómo se llama cada juego. Este llega paginado
    con el título ya dentro.
    """

    STORE = Stores.GOG
    LABEL = "GOG"

    def __init__(self, session: GOGSession | None = None, cacher=None, http=None):
        super().__init__(cacher)
        self.session = session or GOGSession()
        self._http = http

    def is_ready(self) -> tuple[bool, str]:
        if not self.session.is_logged_in():
            return False, "no has iniciado sesión en GOG (Opciones → Cuentas)"
        return True, ""

    def _fetch_remote(self) -> Sequence[dict]:
        import requests

        http = self._http or requests
        # Fuera del bucle: renueva el token una vez, no una por página.
        headers = self.session.bearer_headers()

        juegos: list[dict] = []
        pagina = 1
        while pagina <= MAX_PAGINAS:
            respuesta = http.get(
                PRODUCTS_URL,
                params={"mediaType": 1, "page": pagina},
                headers=headers,
                timeout=TIMEOUT,
            )
            respuesta.raise_for_status()
            datos = respuesta.json()

            productos = datos.get("products") or []
            juegos.extend(self._normalizar(p) for p in productos)

            total = int(datos.get("totalPages") or 1)
            if pagina >= total or not productos:
                break
            pagina += 1
        else:
            logger.warning(
                f"GOG: se ha parado en la página {MAX_PAGINAS}; puede faltar "
                "parte de la biblioteca"
            )

        return juegos

    @staticmethod
    def _normalizar(producto: dict) -> dict:
        """
        El producto de GOG con las claves que espera su resolver.

        `app_name` y `title` son las que lee `GOGResolver`, heredadas
        de cómo las escribía Heroic. Se añaden en vez de renombrar: el resto
        del producto se guarda tal cual porque no cuesta nada y evita tener
        que volver a pedirlo si algún día hace falta otro campo.
        """
        return {
            **producto,
            "app_name": str(producto.get("id") or ""),
            "title": producto.get("title") or "",
        }

    @staticmethod
    def store_id(raw: dict) -> str:
        return str(raw.get("app_name") or raw.get("id") or "")
