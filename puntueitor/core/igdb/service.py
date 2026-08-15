import json
import logging
import time
import igdbpy
from pathlib import Path
from typing import Any

from puntueitor.core.config import ConfigManager
from puntueitor.core.cachers.igdb_cacher import IGDBCacher
from puntueitor.core import paths
from puntueitor.core.diagnostics import describe_error, is_auth_error, is_offline

logger = logging.getLogger(__name__)


class IGDBError(RuntimeError):
    """
    Fallo hablando con IGDB, con el mensaje ya listo para enseñar.

    Se parte en dos subclases porque lo que el usuario tiene que hacer es
    distinto y opuesto: con `IGDBAuthError` hay que ir a Configuración a tocar
    las credenciales, y con `IGDBUnavailableError` no hay nada que tocar, hay
    que esperar o mirar la red. Antes las dos eran el mismo `RuntimeError` con
    el texto en crudo de la librería.
    """


class IGDBAuthError(IGDBError):
    """Las credenciales de IGDB faltan o las han rechazado."""


class IGDBUnavailableError(IGDBError):
    """No se pudo llegar a IGDB: sin red, caído o limitando peticiones."""


class IGDBService:

    FIELDS = "fields name,genres.name,aggregated_rating,cover.url,rating,storyline,first_release_date,total_rating,external_games.uid,external_games.external_game_source; "
    MAX_RETRIES = 2
    INITIAL_DELAY = 0.3
    RETRYABLE_ERRORS = ("timeout", "connection", "reset", "refused", "temporary", "503", "429", "502", "504")

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        cache_dir: str | Path | None = None,
    ) -> None:
        """ Motor de acceso a IGDB usando igdbpy.
         Gestiona el token y expone un wrapper autenticado. """
        config = ConfigManager().get
        self.client_id = client_id or config.igdb_client_id
        self.client_secret = client_secret or config.igdb_client_secret

        if cache_dir is None:
            cache_dir = paths.data_dir()
        db_path = Path(cache_dir) / "puntueitor.db"
        logger.debug(f"caché de IGDB en {db_path}")
        self.cacher = IGDBCacher(db_path)

        self.token = self._load_token_from_disk()
        self.wrapper = None
    
    # ---------------------------
    # TOKEN MANAGEMENT
    # ---------------------------

    def _is_token_expired(self, token: dict) -> bool:
        return int(time.time()) >= token["expires_at"]
    
    def _ensure_token(self) -> None:
        if self.token is not None and not self._is_token_expired(self.token):
            if self.wrapper is not None:
                return
            self.wrapper = igdbpy.IgdbWrapper(
                client_id=self.client_id,
                access_token=self.token["access_token"],
            )
            return

        # Antes de salir a la red: sin credenciales no hay nada que intentar,
        # y el error que devolvía IGDB por no mandarlas no se parecía en nada
        # a "te falta ponerlas".
        if not self.client_id or not self.client_secret:
            raise IGDBAuthError(
                "faltan las credenciales de IGDB (Client ID y Client Secret). "
                "Ponlas en Opciones → Configuración"
            )

        try:
            raw_token = igdbpy.utils.generate_api_key(
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            now = int(time.time())
            self.token = {
                "access_token": raw_token.access_token,
                "expires_in": raw_token.expires_in,
                "token_type": raw_token.token_type,
                "expires_at": now + int(raw_token.expires_in),
            }
            self._save_token_to_disk(self.token)
            self.wrapper = igdbpy.IgdbWrapper(
                client_id=self.client_id,
                access_token=self.token["access_token"],
            )
        except Exception as e:
            detalle = describe_error(e, "IGDB")
            logger.error(f"no se pudo autenticar contra IGDB: {detalle}")
            if is_offline(e):
                raise IGDBUnavailableError(detalle) from e
            if is_auth_error(e):
                raise IGDBAuthError(
                    "IGDB ha rechazado las credenciales. Comprueba el Client "
                    "ID y el Client Secret en Opciones → Configuración"
                ) from e
            # Sin código de estado no se puede afirmar cuál de las dos cosas
            # es; se cuenta lo que se sabe y no se inventa un culpable.
            raise IGDBError(detalle) from e
    
    def _load_token_from_disk(self) -> dict | None:
        if not paths.igdb_token_file().exists():
            return None
        
        try:
            data = json.loads(paths.igdb_token_file().read_text())
            for key in ("access_token", "expires_in", "token_type", "expires_at"):
                if key not in data:
                    return None
            return data
        except (json.JSONDecodeError, OSError):
            return None

            
    def _save_token_to_disk(self, token: dict) -> None:
        paths.igdb_token_file().parent.mkdir(parents=True, exist_ok=True)
        paths.igdb_token_file().write_text(json.dumps(token))

    
    # ---------------------------
    # API HELPER
    # ---------------------------
    def _is_retryable_error(self, error: Exception) -> bool:
        error_str = str(error).lower()
        return any(e in error_str for e in self.RETRYABLE_ERRORS)

    def _query_games(self, query: str) -> list[dict[str, Any]]:
        """
        Ejecuta una query contra IGDB y devuelve una lista de juegos.
        Implementa retry selectivo con backoff exponencial.
        """
        self._ensure_token()
        delay = self.INITIAL_DELAY
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                raw = self.wrapper.make_request(
                    endpoint="games",
                    field_query=query,
                )
            except Exception as e:
                # Ningún error se interpreta como "el juego no existe": eso
                # acababa marcando juegos válidos como desconocidos para
                # siempre por un fallo puntual del cliente.
                last_error = e
                if attempt < self.MAX_RETRIES - 1 and self._is_retryable_error(e):
                    logger.warning(
                        f"IGDB falló (intento {attempt + 1} de "
                        f"{self.MAX_RETRIES}): {describe_error(e, 'IGDB')}. "
                        f"Se reintenta en {delay}s"
                    )
                    time.sleep(delay)
                    delay *= 2
                continue

            if not isinstance(raw, list):
                raise RuntimeError("Unexpected IGDB response format")

            return raw

        detalle = describe_error(last_error, "IGDB") if last_error else "sin detalle"
        if last_error is not None and is_auth_error(last_error):
            raise IGDBAuthError(detalle) from last_error
        raise IGDBUnavailableError(
            f"{detalle} (tras {self.MAX_RETRIES} intentos)"
        ) from last_error
    
    
    def _cachear_list(self, query: list[dict]) -> None:
        for r in query:
            try:
                self.cacher.save_game(r)
            except Exception as e:
                logger.warning(
                    f"no se pudo guardar en caché el juego {r.get('id')}: {e}"
                )

    
    # --------------------------- 
    # PUBLIC API
    # ---------------------------
    
    def get_game(
        self,
        igdb_id: int,
        refresh: bool = False
    ) -> dict:
        """
        Devuelve un juego de IGDB por id.
        - refresh: fuerza nueva consulta a IGDB y no lee de cache
        """
        # Intentar caché
        if not refresh:
            data = self.cacher.get_game(igdb_id)
            if data:
                return data
            if not self.cacher.available:
                raise ValueError(f"IGDB cache unavailable for game {igdb_id}")

        # Consultar IGDB
        query = (
            f"{self.FIELDS}"
            f"where id = {igdb_id};"
            f"limit 1;"
        )

        results = self._query_games(query)

        if not results:
            raise ValueError(f"IGDB game not found: {igdb_id}")

        self._cachear_list(results)
        return results[0]
    
    def search_by_title(self,
        title: str,
        limit:int = 5,
        cache_results: bool = True
    ) -> list[dict]:
        query = (
            f'{self.FIELDS}'
            f'limit {limit}; '
            f'search "{title}";'
        )
        results = self._query_games(query)
        if cache_results:
            self._cachear_list(results)
        return results
        
    def search_by_external_game(
        self,
        source_id: int,
        external_uid: str,
        limit: int = 5,
        cache_results: bool = True
    ) -> list[dict]:
        query = (
            f"{self.FIELDS}"
            f"where external_games.external_game_source = {source_id} "
            f'& external_games.uid = "{external_uid}";'
            f"limit {limit};"
        )
        results = self._query_games(query)
        if cache_results:
            self._cachear_list(results)
        return results

    def search_by_slug(
        self,
        slug: str,
        cache_results: bool = True
    ) -> list[dict]:
        """Busca un juego en IGDB por su slug (URL-friendly identifier)."""
        query = (
            f"{self.FIELDS}"
            f'where slug = "{slug}";'
            "limit 1;"
        )
        results = self._query_games(query)
        if cache_results:
            self._cachear_list(results)
        return results

    
