"""
Sesiones de tienda: iniciarlas en el navegador y mantenerlas vivas.

El token se guarda en `CACHE_DIR` con el mismo criterio que el de IGDB
(`TokenStore`), y el flujo común —canjear, renovar, caducar— vive en
`OAuthSession`. Cada tienda solo aporta sus URLs.
"""
from puntueitor.core.auth.errors import AuthError, NotLoggedIn, SessionExpired
from puntueitor.core.auth.oauth import OAuthSession
from puntueitor.core.auth.paste import extract_code, extract_steam_id
from puntueitor.core.auth.token_store import TokenStore

__all__ = [
    "AuthError", "NotLoggedIn", "SessionExpired",
    "OAuthSession", "TokenStore", "extract_code", "extract_steam_id",
]
