"""
Sacar el código de lo que el usuario acaba de pegar.

Ninguna de las tres tiendas nos deja recoger el redirect: GOG, Epic y Amazon
tienen su `redirect_uri` fijada del lado del servidor hacia un dominio suyo,
así que no hay `localhost` al que volver y el navegador nunca regresa a
Puntueitor. La única vía sin empotrar un navegador entero en la aplicación es
que el usuario copie y pegue.

Lo que sí podemos es no hacérselo pasar mal: se acepta la URL ENTERA de la
barra de direcciones, el JSON que enseña Epic en su página de redirección o
el código pelado. Nadie tiene que buscar un parámetro a mano dentro de una
URL de cuatrocientos caracteres.
"""
import json
import logging
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


def extract_code(pegado: str, params: tuple[str, ...]) -> str:
    """
    El código que hay dentro de `pegado`, o "" si no se reconoce nada.

    `params` son los nombres con los que esa tienda llama a su código, en
    orden de preferencia.
    """
    texto = (pegado or "").strip().strip('"').strip("'")
    if not texto:
        return ""

    for extractor in (_de_json, _de_url):
        codigo = extractor(texto, params)
        if codigo:
            return codigo

    # Si era una URL o un JSON y hemos llegado hasta aquí, es que NO traía el
    # código. Mandarla entera como si lo fuera solo consigue que la tienda
    # conteste un 400 y que el usuario crea que se ha equivocado de cuenta.
    if "://" in texto or texto.startswith("{"):
        logger.debug("lo pegado es una dirección, pero sin código dentro")
        return ""

    # Un código pelado. Se acepta tal cual, pero solo si no tiene pinta de
    # ser otra cosa: espacios dentro casi siempre significan que se ha
    # pegado media frase.
    if " " not in texto and "\n" not in texto:
        return texto

    logger.debug("lo pegado no parece un código, ni una URL, ni un JSON")
    return ""


def _de_json(texto: str, params: tuple[str, ...]) -> str:
    """Epic enseña un JSON en su página de redirección; se acepta entero."""
    if not texto.startswith("{"):
        return ""
    try:
        data = json.loads(texto)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""

    for nombre in params:
        valor = data.get(nombre)
        if valor:
            return str(valor)
    return ""


def _de_url(texto: str, params: tuple[str, ...]) -> str:
    """De la URL de la barra de direcciones, mirando query Y fragmento."""
    if "://" not in texto:
        return ""

    partes = urlparse(texto)
    # El fragmento también: algunos flujos devuelven los parámetros detrás
    # de la almohadilla, donde `parse_qs(query)` no llega.
    campos = {**parse_qs(partes.query), **parse_qs(partes.fragment)}

    for nombre in params:
        valores = campos.get(nombre)
        if valores and valores[0]:
            return valores[0]
    return ""


def extract_steam_id(pegado: str) -> str:
    """
    El SteamID de 17 cifras que hay en `pegado`.

    Steam vuelve del login por OpenID con
    `openid.claimed_id=https://steamcommunity.com/openid/id/7656119...`, pero
    aquí también vale pegar la URL del perfil, o el número a secas: para el
    usuario es "pega esto" en las cuatro tiendas, y quién lo escribió de qué
    forma no es asunto suyo.
    """
    texto = (pegado or "").strip()
    if not texto:
        return ""

    if texto.isdigit():
        return texto

    if "://" in texto:
        partes = urlparse(texto)
        campos = parse_qs(partes.query)
        candidatos = campos.get("openid.claimed_id") or []
        candidatos.append(partes.path)
        for candidato in candidatos:
            trozo = str(candidato).rstrip("/").rsplit("/", 1)[-1]
            if trozo.isdigit():
                return trozo

    return ""
