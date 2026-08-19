class AuthError(Exception):
    """Algo falló hablando con el servidor de sesiones de una tienda."""


class NotLoggedIn(AuthError):
    """No hay sesión guardada: hay que iniciarla desde Opciones."""


class SessionExpired(AuthError):
    """
    Había sesión, pero ya no vale y no se ha podido renovar.

    Se distingue de `NotLoggedIn` porque al usuario se le dice otra cosa:
    una es "inicia sesión" y la otra "tu sesión ha caducado, vuelve a
    entrar". Y porque quien la recibe sabe que la copia guardada de la
    biblioteca sigue siendo suya y se puede seguir usando.
    """
