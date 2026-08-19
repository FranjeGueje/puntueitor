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

#: Cuántas páginas se piden a la vez. Una biblioteca grande no pasa de una
#: docena de páginas, así que con esto van todas de golpe.
HILOS = 8

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
        self._headers_cache: dict | None = None

    def is_ready(self) -> tuple[bool, str]:
        if not self.session.is_logged_in():
            return False, "no has iniciado sesión en GOG (Opciones → Cuentas)"
        return True, ""

    def _fetch_remote(self) -> Sequence[dict]:
        """
        La biblioteca entera, pidiendo las páginas 2..N a la vez.

        La primera respuesta ya dice cuántas páginas hay (`totalPages`), así
        que no hay que ir descubriéndolas de una en una: en cuanto vuelve, se
        piden todas las demás en paralelo. Con 411 juegos son 9 páginas, de
        4,8 s a poco más de una.
        """
        from concurrent.futures import ThreadPoolExecutor

        primera = self._pagina(1)
        juegos = [self._normalizar(p) for p in primera.get("products") or []]

        total = min(int(primera.get("totalPages") or 1), MAX_PAGINAS)
        if total <= 1:
            return juegos

        with ThreadPoolExecutor(max_workers=min(total - 1, HILOS)) as pool:
            for datos in pool.map(self._pagina, range(2, total + 1)):
                juegos.extend(
                    self._normalizar(p) for p in datos.get("products") or []
                )

        return juegos

    def _pagina(self, numero: int) -> dict:
        import requests

        http = self._http or requests
        respuesta = http.get(
            PRODUCTS_URL,
            params={"mediaType": 1, "page": numero},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        respuesta.raise_for_status()
        return respuesta.json()

    def _headers(self) -> dict:
        """
        Las cabeceras, con el token renovado UNA sola vez.

        Se memoriza para la duración de la petición: si cada página pidiera
        su token, nueve páginas en paralelo podrían disparar nueve
        renovaciones a la vez.
        """
        if self._headers_cache is None:
            self._headers_cache = self.session.bearer_headers()
        return self._headers_cache

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
