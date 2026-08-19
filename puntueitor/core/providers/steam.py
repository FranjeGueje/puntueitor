import logging
from collections.abc import Sequence

from puntueitor.core.models import Stores
from puntueitor.core.providers.base import LibraryProvider

logger = logging.getLogger(__name__)


class SteamProvider(LibraryProvider):
    """
    La biblioteca de Steam, por su Web API oficial (`GetOwnedGames`).

    Es la única de las cuatro que va por una API pública y documentada, así
    que no hay OAuth: basta con la API key del usuario y su SteamID. Lo que
    antes se leía de `libraryfolders.vdf` no hace falta —y además solo veía
    lo INSTALADO, no lo que tienes comprado, que es lo que le interesa a
    Puntueitor.
    """

    STORE = Stores.STEAM
    LABEL = "Steam"

    def __init__(self, api_key: str = "", user_id: int = 0, cacher=None):
        super().__init__(cacher)
        self.api_key = api_key or ""
        self.user_id = int(user_id or 0)

    def is_ready(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, (
                "no hay API key de Steam (Opciones → Cuentas)"
            )
        if not self.user_id:
            return False, (
                "no hay Steam ID (Opciones → Cuentas)"
            )
        return True, ""

    def _fetch_remote(self) -> Sequence[dict]:
        # Dentro: el cliente arrastra `requests` y este módulo lo importa
        # gente que solo quiere saber qué tiendas hay.
        from puntueitor.core.raw.steam import SteamApi

        games = SteamApi().owned_games(self.api_key, self.user_id)
        if games is None:
            # None es "la petición falló", que no es lo mismo que "no tienes
            # juegos". Se convierte en excepción para que `fetch` lo trate
            # como fallo y tire de la copia guardada.
            raise ConnectionError("no se pudo consultar la biblioteca de Steam")
        return games

    @staticmethod
    def store_id(raw: dict) -> str:
        # El mismo campo que mira `SteamIGDBResolver._extract_id`.
        return str(raw.get("appid") or "")

    @staticmethod
    def store_title(raw: dict) -> str:
        return raw.get("name") or ""
