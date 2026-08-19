import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence

from puntueitor.core.auth.errors import AuthError
from puntueitor.core.cachers.store_library_cacher import StoreLibraryCacher
from puntueitor.core.diagnostics import describe_error
from puntueitor.core.models import Stores

logger = logging.getLogger(__name__)


class LibraryProvider(ABC):
    """
    De dónde salen los juegos crudos de una tienda.

    Antes esto vivía dentro de `load_library` como dos closures —una que
    llamaba a la API de Steam y otra que leía los JSON de Heroic—, y el
    pipeline tenía que saber de ambas. Aquí cada tienda sabe pedirse a sí
    misma y el pipeline solo recorre una lista de proveedores.

    El contrato es el diccionario CRUDO de la tienda, tal cual lo sirve su
    API: quien lo interpreta es el resolver de esa tienda
    (`core/resolvers/`), que ya sabe qué claves mirar. Un proveedor que
    «normalizara» los campos rompería a los resolvers y no ganaría nada.
    """

    #: Tienda que sirve este proveedor.
    STORE: Stores

    #: Cómo se llama en los mensajes al usuario ("Steam", "GOG"...).
    LABEL: str

    def __init__(self, cacher: StoreLibraryCacher | None = None):
        self._cacher = cacher if cacher is not None else StoreLibraryCacher(self.STORE)

    # ──────────────────────────────
    # Lo que aporta cada tienda
    # ──────────────────────────────

    @abstractmethod
    def is_ready(self) -> tuple[bool, str]:
        """
        Si se puede llamar a la tienda ahora mismo y, si no, por qué.

        El motivo se le enseña al usuario tal cual, así que tiene que decirle
        QUÉ HACER —«no hay API key: Opciones → Cuentas»—, no solo qué
        ha fallado.
        """

    @abstractmethod
    def _fetch_remote(self) -> Sequence[dict]:
        """Pide la biblioteca a la tienda. Puede lanzar; el que llama lo trata."""

    @staticmethod
    @abstractmethod
    def store_id(raw: dict) -> str:
        """El identificador del juego dentro de la tienda."""

    @staticmethod
    def store_title(raw: dict) -> str:
        """El nombre del juego EN SU TIENDA, que no es el que le da IGDB."""
        return raw.get("title") or raw.get("name") or ""

    # ──────────────────────────────
    # Política común
    # ──────────────────────────────

    def fetch(self, *, refresh: bool = False) -> Sequence[dict]:
        """
        Los juegos crudos de la tienda, de la web o de la copia guardada.

        Nunca lanza y nunca devuelve vacío teniendo datos guardados. Esa es
        toda la gracia: sin conexión, con la sesión caducada o con la tienda
        caída, la biblioteca sigue apareciendo —la de la última vez— en lugar
        de desaparecer sin explicación. El log dice siempre de dónde salió.
        """
        cached = self._cacher.get_games()

        if not refresh and cached is not None:
            logger.debug(f"{self.LABEL}: {len(cached)} juegos de la copia guardada")
            return cached

        ready, motivo = self.is_ready()
        if not ready:
            return self._degradar(cached, motivo)

        try:
            items = list(self._fetch_remote())
        except AuthError as error:
            # Estos ya vienen redactados para el usuario, y con el "vuelve a
            # iniciar sesión" dentro. Pasarlos por `describe_error` los
            # convertiría en un "error desconocido" mucho menos útil.
            return self._degradar(cached, str(error))
        except Exception as error:
            return self._degradar(cached, describe_error(error, self.LABEL))

        if not items:
            # La tienda contestó, pero sin juegos. Si teníamos algo guardado
            # casi siempre es un fallo suyo y no que hayas vendido tu cuenta,
            # así que no se tira la copia buena.
            return self._degradar(
                cached, f"{self.LABEL} no devolvió ningún juego",
            )

        self._cacher.save_games(items, self.store_id, self.store_title)
        logger.info(f"{self.LABEL}: {len(items)} juegos en tu biblioteca")
        return items

    def _degradar(self, cached: list[dict] | None, motivo: str) -> Sequence[dict]:
        """Cae a la copia guardada, diciendo por qué."""
        if cached:
            logger.warning(
                f"{self.LABEL}: {motivo}. Se usan los {len(cached)} juegos de "
                "la última vez; refresca cuando se arregle"
            )
            return cached

        logger.warning(f"{self.LABEL}: {motivo}. No hay copia guardada: 0 juegos")
        return ()
