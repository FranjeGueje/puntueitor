import json
import logging
import time
from pathlib import Path

from puntueitor.core import paths

logger = logging.getLogger(__name__)

#: Margen antes de dar un token por caducado. Renovar un token que aún vale
#: no cuesta nada; que caduque a mitad de una carga de mil juegos, sí.
_MARGEN_SEGUNDOS = 300


class TokenStore:
    """
    El token de sesión de una tienda, guardado entre arranques.

    Mismo trato que el de IGDB (`core/igdb/service.py`): un JSON en
    `CACHE_DIR`, sin cifrar. No es un descuido: es un token de solo lectura
    de TU biblioteca, se renueva solo y, si se pierde, lo único que pasa es
    que hay que volver a iniciar sesión. Meter un llavero del sistema
    añadiría una dependencia con backend propio —y en Steam Deck, dentro de
    un binario de PyInstaller, un modo más de fallar— a cambio de proteger
    algo que ya está tan protegido como el resto de `~/.cache`.

    Lo que sí se cuida: el fichero se escribe solo para el usuario (0600) y
    el token no aparece nunca en el log.
    """

    def __init__(self, store: str, path: str | Path | None = None):
        self.store = str(store)
        self.path = Path(path) if path else paths.store_token_file(self.store)
        self._data: dict | None = None

    # ──────────────────────────────
    # Lectura
    # ──────────────────────────────

    @property
    def data(self) -> dict:
        """Lo guardado, o `{}` si no hay nada legible."""
        if self._data is None:
            self._data = self._load()
        return self._data

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as fichero:
                data = json.load(fichero)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as error:
            logger.warning(
                f"la sesión guardada de {self.store} no se puede leer ({error}); "
                "habrá que iniciar sesión otra vez"
            )
            return {}

    @property
    def access_token(self) -> str:
        return self.data.get("access_token") or ""

    @property
    def refresh_token(self) -> str:
        return self.data.get("refresh_token") or ""

    def is_expired(self, margin: int = _MARGEN_SEGUNDOS) -> bool:
        """
        Si el token ya no sirve (o está a punto de no servir).

        Sin `expires_at` se da por caducado: renovar de más es gratis, y
        seguir con un token muerto es una petición fallida y una tienda
        vacía.
        """
        expires_at = self.data.get("expires_at")
        if not expires_at:
            return True
        return time.time() >= float(expires_at) - margin

    def has_session(self) -> bool:
        """Si hay algo con lo que trabajar, aunque haya que renovarlo."""
        return bool(self.access_token or self.refresh_token)

    # ──────────────────────────────
    # Escritura
    # ──────────────────────────────

    def save(self, payload: dict) -> None:
        """
        Guarda la respuesta del servidor de tokens.

        `expires_in` (segundos desde ahora) se convierte a `expires_at`
        (momento absoluto) al guardar: un plazo relativo dentro de un fichero
        que sobrevive al reinicio no significa nada.
        """
        data = dict(payload)
        expires_in = data.pop("expires_in", None)
        if expires_in:
            try:
                data["expires_at"] = time.time() + float(expires_in)
            except (TypeError, ValueError):
                logger.debug(f"{self.store}: expires_in ilegible ({expires_in!r})")

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporal = self.path.with_suffix(".tmp")
            with open(temporal, "w", encoding="utf-8") as fichero:
                json.dump(data, fichero)
            # Antes de publicarlo, no después: si no, hay un instante en que
            # el token es legible por cualquiera de la máquina.
            temporal.chmod(0o600)
            temporal.replace(self.path)
            self._data = data
        except OSError as error:
            logger.warning(
                f"no se pudo guardar la sesión de {self.store}: {error}. "
                "Funcionará esta vez, pero habrá que iniciar sesión al volver"
            )
            self._data = data

    def clear(self) -> None:
        """Cierra la sesión: olvida el token."""
        self._data = {}
        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:
            logger.warning(f"no se pudo borrar la sesión de {self.store}: {error}")
