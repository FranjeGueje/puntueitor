import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from puntueitor.core.auth.epic import USER_AGENT, EpicSession
from puntueitor.core.models import Stores
from puntueitor.core.providers.base import LibraryProvider

logger = logging.getLogger(__name__)

ASSETS_URL = (
    "https://launcher-public-service-prod06.ol.epicgames.com"
    "/launcher/api/public/assets/Windows?label=Live"
)
CATALOG_URL = (
    "https://catalog-public-service-prod06.ol.epicgames.com"
    "/catalog/api/shared/namespace/{namespace}/bulk/items"
)
STORE_URL_PREFIX = "https://www.epicgames.com/store/product/"

#: El "namespace" del mercado de Unreal Engine. Ahí no hay juegos, hay
#: plugins y assets de desarrollo: si no se filtra, la biblioteca se llena de
#: cosas que nadie ha jugado nunca.
NAMESPACE_UNREAL = "ue"

#: Cuántas fichas de catálogo se piden a la vez. Epic obliga a una petición
#: por juego (el catálogo va por `namespace`, y casi cada juego tiene el
#: suyo), así que sin paralelismo una biblioteca grande tarda minutos. Ocho
#: es lo bastante rápido sin que Epic empiece a devolver 429.
HILOS = 8

TIMEOUT = 20


class EpicProvider(LibraryProvider):
    """
    La biblioteca de Epic, por la API del Epic Games Launcher.

    Van dos pasos, y no es cosa nuestra: el primero
    (`launcher/api/public/assets`) dice QUÉ tienes, con identificadores pero
    sin un solo nombre legible; el segundo (`catalog`) traduce cada
    identificador a su ficha. Es lo mismo que hacen Legendary y Heroic, y es
    la parte lenta de un refresco de Epic.
    """

    STORE = Stores.EPIC
    LABEL = "Epic"

    def __init__(self, session: EpicSession | None = None, cacher=None, http=None):
        super().__init__(cacher)
        self.session = session or EpicSession()
        self._http = http

    def is_ready(self) -> tuple[bool, str]:
        if not self.session.is_logged_in():
            return False, "no has iniciado sesión en Epic (Opciones → Cuentas)"
        return True, ""

    def _fetch_remote(self) -> Sequence[dict]:
        headers = {**self.session.bearer_headers(), "User-Agent": USER_AGENT}

        assets = self._get(ASSETS_URL, headers) or []
        interesantes = [
            asset for asset in assets
            if asset.get("namespace") != NAMESPACE_UNREAL and asset.get("appName")
        ]
        logger.debug(
            f"Epic: {len(assets)} elementos, {len(interesantes)} tras quitar "
            "los del mercado de Unreal"
        )
        if not interesantes:
            return []

        with ThreadPoolExecutor(max_workers=HILOS) as pool:
            fichas = list(pool.map(
                lambda asset: self._ficha(asset, headers), interesantes,
            ))

        return [juego for juego in fichas if juego is not None]

    # ──────────────────────────────
    # Catálogo
    # ──────────────────────────────

    def _ficha(self, asset: dict, headers: dict) -> dict | None:
        """
        El asset con su nombre y su enlace de tienda, o None si no es un juego.

        Un fallo aquí se traga a propósito: son cientos de peticiones y que
        una se pierda no puede tirar el refresco entero. Ese juego se queda
        fuera esta vez y vuelve en el siguiente.
        """
        namespace = asset.get("namespace")
        item_id = asset.get("catalogItemId")
        if not namespace or not item_id:
            return None

        try:
            datos = self._get(
                CATALOG_URL.format(namespace=namespace),
                headers,
                params={
                    "id": item_id,
                    "includeDLCDetails": "false",
                    "includeMainGameDetails": "true",
                    "country": "ES",
                    "locale": "es-ES",
                },
            )
        except Exception as error:
            logger.debug(f"Epic: sin ficha de {asset.get('appName')}: {error}")
            return None

        item = (datos or {}).get(item_id)
        if not isinstance(item, dict) or not self._es_juego(item):
            return None

        return {
            "app_name": asset["appName"],
            "title": item.get("title") or "",
            "store_url": self._store_url(item),
            "namespace": namespace,
            "catalog_item_id": item_id,
        }

    @staticmethod
    def _es_juego(item: dict) -> bool:
        """
        Fuera todo lo que no sea un juego base.

        `mainGameItem` solo lo traen los DLC —apunta al juego del que
        cuelgan—, y sin este filtro cada expansión entraría como si fuera un
        título aparte que puntuar.
        """
        if item.get("mainGameItem"):
            return False

        categorias = {
            str(c.get("path", "")).lower()
            for c in item.get("categories") or []
            if isinstance(c, dict)
        }
        if "applications" in categorias and "games" not in categorias:
            return False
        return "addons" not in categorias

    @staticmethod
    def _store_url(item: dict) -> str:
        """
        El enlace del juego en la tienda, que es por donde empieza a buscar
        `EpicResolver`: del slug saca el juego en IGDB sin depender del
        título, que es lo que más falla.
        """
        slug = item.get("productSlug") or ""
        if not slug:
            for mapeo in item.get("catalogNs", {}).get("mappings") or ():
                if isinstance(mapeo, dict) and mapeo.get("pageSlug"):
                    slug = mapeo["pageSlug"]
                    break
        # Epic arrastra slugs con "/home" pegado detrás de los antiguos.
        slug = str(slug).split("/")[0]
        return f"{STORE_URL_PREFIX}{slug}" if slug else ""

    # ──────────────────────────────

    def _get(self, url: str, headers: dict, params: dict | None = None):
        import requests

        http = self._http or requests
        respuesta = http.get(url, headers=headers, params=params, timeout=TIMEOUT)
        respuesta.raise_for_status()
        return respuesta.json()

    @staticmethod
    def store_id(raw: dict) -> str:
        return str(raw.get("app_name") or "")
