"""
Qué es una tienda para Puntueitor.

Todo lo que el programa necesita saber de una tienda cabe aquí dentro, y esa
es la idea: antes lo mismo vivía repartido en once ficheros —el color en el
carrusel, la etiqueta en dos menús, la clase de sesión en un servicio, la
bandera de configuración en otro— y había que mantenerlos sincronizados a
mano. Eso ya falló dos veces: filas de menú que se pintaban bien pero no
hacían nada al elegirlas, y una tienda colándose en una lista donde no
pintaba nada.

Añadir una tienda es escribir su módulo en este paquete. Lo único que se
queda fuera son dos líneas que no pueden estar aquí: su miembro en el enum
`Stores` (la clave con la que se guardan sus juegos en la base de datos) y su
campo en `Config` (lo que se escribe en `config.json`). Hay un test que
comprueba que no se olvidan.
"""
from collections.abc import Callable
from dataclasses import dataclass

from puntueitor.core.models import Stores


@dataclass(frozen=True)
class StoreSpec:
    """Una tienda, entera."""

    #: El miembro del enum. Es la clave con la que se guardan sus juegos, así
    #: que cambiarla invalidaría la biblioteca de todo el mundo.
    store: Stores

    #: Cómo se llama al hablarle al usuario: "GOG", "Epic", "Amazon".
    label: str

    #: El campo de `Config` que la activa (`"gog_is_active"`).
    config_flag: str

    #: El color de su estuche en el carrusel.
    color: tuple[float, float, float]

    #: Cómo se construye su proveedor de biblioteca. Es un invocable y no la
    #: clase porque algunas necesitan argumentos de la configuración (Steam
    #: quiere su clave y su id).
    provider: Callable

    #: Su resolver contra IGDB.
    resolver: type

    #: Cómo se construye su sesión, o None si la tienda NO TIENE sesión que
    #: iniciar. Steam es el caso: no ofrece OAuth a terceros, así que se
    #: configura con su API key. Que eso se declare aquí —y no en una lista
    #: aparte de "tiendas con sesión"— es justo lo que evita que alguien
    #: recorra el enum entero y le pinte a Steam un botón de conectar.
    session: Callable | None = None

    #: Qué se le pide pegar al usuario al volver del navegador. Vacío en las
    #: que no tienen sesión.
    paste_hint: str = ""

    #: Cómo se abrevia en el chip del banner del estuche, donde no caben más
    #: de cuatro o cinco letras ("AMZN" por Amazon, "ITCH" por itch.io).
    #: Vacío significa "el nombre en mayúsculas", que es lo que ya vale para
    #: Steam, GOG y Epic — ver `banner_text`.
    #:
    #: Vive aquí y no en `gui3d/case_banner.py` porque una tabla de tiendas
    #: escrita a mano en el frontend es justo lo que este registro existe
    #: para no tener: la que había reventaba el carrusel entero con un
    #: `KeyError` en cuanto apareció una tienda que no estaba en ella.
    banner_label: str = ""

    #: Si un juego suyo se puede volver a identificar por su id de tienda.
    #: Amazon no: sus juegos se buscan solo por título, así que ahí la única
    #: vía es buscar a mano (ver `services/unknown_actions.py`).
    resolvable_by_id: bool = True

    @property
    def key(self) -> str:
        """La clave en texto (`"gog"`), que es como viaja por la config."""
        return str(self.store)

    @property
    def banner_text(self) -> str:
        """Lo que se escribe en su chip del banner."""
        return self.banner_label or self.label.upper()

    @property
    def has_session(self) -> bool:
        return self.session is not None
