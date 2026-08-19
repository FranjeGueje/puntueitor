"""
Traducir un fallo a algo que se pueda leer y, sobre todo, arreglar.

Todo lo que puede salir mal aquí sale de la red o de la configuración —no hay
internet, la clave no vale, el perfil de Steam es privado, la carpeta de
Heroic no está donde se dijo—, y en el log todo eso llegaba igual: un
`repr` de una excepción de `requests`, cuando llegaba algo. Quien lo lee no
quiere saber qué excepción se lanzó, quiere saber qué tiene que tocar.

Un solo sitio para esa traducción, y lo usan las dos cosas que la necesitan:
el log y los avisos de las dos interfaces (que enseñaban `f"Error: {e}"`).

Aquí NO se comprueba nada por la red: no se hace ping ni se llama a nadie
para "verificar si hay internet". Se mira la excepción que ya ha ocurrido y su
código de estado si lo trae, y punto.
"""
import logging
import socket

logger = logging.getLogger(__name__)

#: Trozos de mensaje que delatan que el problema es de DNS o de conexión.
#: Hace falta mirar el texto además del tipo porque no toda la aplicación usa
#: `requests`: `igdbpy` envuelve sus fallos en excepciones propias y lo único
#: que queda del original es la frase.
_SIN_RED = (
    "name or service not known",
    "temporary failure in name resolution",
    "nodename nor servname",
    "no address associated with hostname",
    "connection refused",
    "network is unreachable",
    "connection reset",
    "failed to establish a new connection",
    "max retries exceeded",
)

_TIMEOUT = ("timed out", "timeout")

#: Qué decir para cada código de estado. El 401/403 es el que más importa:
#: es "tu clave no vale", y sin esto se leía como un error de red cualquiera.
#: Redactado para que concuerde con el sujeto que se le pone delante
#: ("Steam ha rechazado las credenciales..."), no como frases sueltas.
_POR_ESTADO = {
    401: "ha rechazado las credenciales: no son válidas o han caducado",
    403: "ha rechazado las credenciales: no son válidas o no dan acceso a esto",
    404: "dice que eso no existe",
    429: "está limitando las peticiones por exceso de uso",
    500: "está fallando por su lado",
    502: "está fallando por su lado",
    503: "no está disponible ahora mismo",
    504: "no está disponible ahora mismo",
}

#: Cuándo merece la pena decirle al usuario dónde se arregla.
_REVISA_CONFIG = " Revísalas en Opciones → Cuentas."


def status_code(error: BaseException) -> int | None:
    """El código HTTP de una excepción de `requests`, si lo trae."""
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def is_offline(error: BaseException) -> bool:
    """¿Este fallo es "no hay internet" y no otra cosa?"""
    if isinstance(error, (socket.gaierror, ConnectionError)):
        return True
    texto = str(error).lower()
    return any(pista in texto for pista in _SIN_RED)


def is_auth_error(error: BaseException) -> bool:
    """¿Este fallo es "tus credenciales no valen"?"""
    return status_code(error) in (401, 403)


def describe_error(error: BaseException, service: str = "") -> str:
    """
    Una frase en español que dice qué ha pasado y, si procede, qué tocar.

    El orden de las comprobaciones importa: sin internet, una petición falla
    ANTES de tener respuesta, así que no hay código de estado que mirar; y al
    revés, un 403 llega por una conexión que funcionó. Primero lo que impide
    llegar, después lo que contestaron.
    """
    quien = service or "el servicio"

    if is_offline(error):
        return f"sin conexión a internet (no se pudo contactar con {quien})"

    texto = str(error).lower()
    if any(pista in texto for pista in _TIMEOUT):
        return f"{quien} no respondió a tiempo"

    estado = status_code(error)
    if estado in _POR_ESTADO:
        frase = f"{quien} {_POR_ESTADO[estado]} [HTTP {estado}]"
        if estado in (401, 403):
            frase += _REVISA_CONFIG
        return frase
    if estado is not None:
        return f"{quien} respondió con un error [HTTP {estado}]"

    detalle = str(error).strip() or type(error).__name__
    return f"{quien}: {detalle}"


def missing_credentials(config) -> list[str]:
    """
    Qué credenciales faltan, POR SU NOMBRE y sin enseñar ningún valor.

    Solo se miran las de las tiendas activas: quien no use Steam no tiene por
    qué ver un aviso sobre su API key en cada arranque.
    """
    faltan = []
    if getattr(config, "steam_is_active", False):
        if not getattr(config, "steam_api_key", ""):
            faltan.append("API key de Steam")
        if not getattr(config, "steam_user_id", 0):
            faltan.append("Steam ID")
    if not getattr(config, "igdb_client_id", ""):
        faltan.append("Client ID de IGDB")
    if not getattr(config, "igdb_client_secret", ""):
        faltan.append("Client Secret de IGDB")
    return faltan
