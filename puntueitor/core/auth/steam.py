"""
Averiguar tu SteamID sin que lo teclees.

Steam no da su API key por OAuth —hay que sacarla a mano de
steamcommunity.com/dev/apikey y no existe forma de automatizarlo—, pero el
NÚMERO de usuario sí se puede obtener entrando por OpenID, que es justo el
dato que más se equivoca la gente al escribirlo a mano.

Se hace por el mismo gesto que las otras tres tiendas —abrir el navegador y
pegar la vuelta— y no con un servidor local, aunque en Steam sí cabría: tener
un flujo distinto en una de las cuatro obliga al usuario a aprender dos
cosas, y a nosotros a mantener dos caminos, a cambio de ahorrar un pegado.

Se omite el `check_authentication` de OpenID a propósito: no estamos
autenticando a nadie contra un servidor nuestro, solo leyendo el número de
usuario del que está sentado delante para pedir SU biblioteca pública. Hoy
ese número se escribe a mano y sin comprobación ninguna, así que esto no
pierde ninguna garantía; y si alguien pega el de otro, lo único que consigue
es ver la biblioteca pública de ese otro en su propio ordenador.
"""
import logging
from urllib.parse import urlencode

from puntueitor.core.auth.paste import extract_steam_id

logger = logging.getLogger(__name__)

LOGIN_URL = "https://steamcommunity.com/openid/login"

#: A dónde manda Steam al terminar. Es una página suya cualquiera: lo que nos
#: interesa viaja en los parámetros de la URL, que es lo que el usuario pega.
RETURN_TO = "https://steamcommunity.com/"


def login_url() -> str:
    """La página que hay que abrir para entrar en Steam."""
    return LOGIN_URL + "?" + urlencode({
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.return_to": RETURN_TO,
        "openid.realm": RETURN_TO,
    })


def steam_id_from(pegado: str) -> str:
    """
    El SteamID que hay en lo que el usuario ha pegado, o "".

    Vale la URL de vuelta del login, la de tu perfil o el número a secas.
    """
    steam_id = extract_steam_id(pegado)
    if not steam_id:
        return ""

    # Los SteamID64 son 17 cifras y empiezan por 7656119. Comprobarlo evita
    # el error más común con diferencia: pegar el id de 3 cifras del perfil,
    # o el nombre personalizado, y quedarse con una biblioteca vacía sin
    # entender por qué.
    if len(steam_id) != 17 or not steam_id.startswith("7656119"):
        logger.warning(
            f"'{steam_id}' no parece un Steam ID de 17 cifras. Si has pegado "
            "la dirección de tu perfil y usa nombre personalizado, entra por "
            "el enlace de inicio de sesión, que sí devuelve el número"
        )
        return ""

    return steam_id
