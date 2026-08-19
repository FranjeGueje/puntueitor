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
#: suyo). Medido con 451 juegos: 21,8 s con 8 hilos, 11,1 s con 16 y 5,6 s
#: con 32. Se elige 16 —la mitad del tiempo— y no 32, para no apretar una API
#: que no es nuestra; el grueso del ahorro viene de no volver a pedir lo ya
#: sabido (ver `_fichas`), no de abrir más conexiones.
HILOS = 16

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

        return self._fichas(interesantes, headers)

    def _fichas(self, assets: list[dict], headers: dict) -> list[dict]:
        """
        La ficha de cada asset, reutilizando lo que ya se sabía.

        Aquí está el grueso del ahorro. La lista de assets no trae títulos,
        así que hay que pedir el catálogo juego a juego —cientos de
        peticiones—, pero **el título, el enlace y el `catalog_item_id` de un
        juego no cambian**: son su ficha pública en la tienda. Como
        `StoreLibraryCacher` guarda el diccionario crudo entero, la ficha de
        la vez anterior ya está en disco.

        Así que solo se pide el catálogo de los assets que no estén en la
        caché o cuyo `catalog_item_id` haya cambiado. Una recarga normal pasa
        de ~450 peticiones a las de los juegos nuevos, y nada más.
        """
        conocidas = self._cacheadas()
        nuevos, reutilizadas = [], []
        for asset in assets:
            cacheada = conocidas.get(asset.get("appName"))
            if cacheada and cacheada.get("catalog_item_id") == asset.get("catalogItemId"):
                reutilizadas.append(cacheada)
            else:
                nuevos.append(asset)

        if reutilizadas:
            logger.info(
                f"Epic: {len(reutilizadas)} fichas ya conocidas, "
                f"{len(nuevos)} por consultar"
            )

        fichas, fallos = [], 0
        if nuevos:
            with ThreadPoolExecutor(max_workers=HILOS) as pool:
                for asset, ficha in zip(nuevos, pool.map(
                    lambda a: self._ficha(a, headers), nuevos,
                )):
                    if ficha is not None:
                        fichas.append(ficha)
                        continue
                    # La ficha no vino. Si la teníamos de antes, se usa esa:
                    # sin esto el juego desaparecería de la biblioteca Y de la
                    # caché, porque `save_games` reemplaza la tienda entera.
                    fallos += 1
                    anterior = conocidas.get(asset.get("appName"))
                    if anterior is not None:
                        fichas.append(anterior)

        if fallos:
            logger.warning(
                f"Epic: {fallos} fichas no se pudieron consultar. Las que ya "
                "se conocían se han conservado; el resto faltará hasta el "
                "próximo refresco"
            )

        return reutilizadas + fichas

    def _cacheadas(self) -> dict[str, dict]:
        """Lo guardado de la vez anterior, indexado por `app_name`."""
        guardadas = self._cacher.get_games() or ()
        return {
            juego["app_name"]: juego
            for juego in guardadas
            if isinstance(juego, dict) and juego.get("app_name")
        }

    # ──────────────────────────────
    # Catálogo
    # ──────────────────────────────

    def _ficha(self, asset: dict, headers: dict) -> dict | None:
        """
        El asset con su nombre y su enlace de tienda.

        **No se filtra nada por tipo.** Hubo un filtro que descartaba DLC y
        aplicaciones, y era una regresión: la v2, que leía la caché de Heroic,
        sí los traía —497 entradas, 41 marcadas como DLC—. Descartándolos aquí
        no llegaban ni al carrusel ni a Desconocidos: desaparecían sin más.
        Quien decide si un juego es identificable es el resolver, y lo que no
        reconozca va a Desconocidos, que es justo para lo que está.

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
        if not isinstance(item, dict):
            return None

        return {
            "app_name": asset["appName"],
            "title": item.get("title") or "",
            "store_url": self._store_url(item),
            "namespace": namespace,
            "catalog_item_id": item_id,
        }

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
