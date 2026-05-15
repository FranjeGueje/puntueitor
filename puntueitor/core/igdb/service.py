import json
import logging
import time
import igdbpy
from pathlib import Path
from typing import Any

from puntueitor.core.config import ConfigManager
from puntueitor.core.cachers.igdb_cacher import IGDBCacher

logger = logging.getLogger(__name__)


class IGDBService:
    TOKEN_PATH = Path.home() / ".cache" / "puntueitor" / "igdb_token.json"
    FIELDS = "fields name,genres.name,aggregated_rating,cover.url,rating,storyline,first_release_date,total_rating; "
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
            base_path = Path(__file__).parent.parent.parent
            cache_dir = base_path / "cache"
        db_path = Path(cache_dir) / "igdb.sqlite" if cache_dir else Path("cache/igdb.sqlite")
        self.cacher = IGDBCacher(db_path)
         
        self.token = self._load_or_generate_token()
        self.wrapper = igdbpy.IgdbWrapper(
            client_id=self.client_id,
            access_token=self.token["access_token"],
        )
    
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
            logger.error(f"Token renewal failed: {e}")
            raise RuntimeError(f"IGDB token renewal failed: {e}") from e
    
    def _load_token_from_disk(self) -> dict | None:
        if not self.TOKEN_PATH.exists():
            return None
        
        try:
            data = json.loads(self.TOKEN_PATH.read_text())
            for key in ("access_token", "expires_in", "token_type", "expires_at"):
                if key not in data:
                    return None
            return data
        except (json.JSONDecodeError, OSError):
            return None

            
    def _save_token_to_disk(self, token: dict) -> None:
        self.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.TOKEN_PATH.write_text(json.dumps(token))

    
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
            except TypeError:
                return []
            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1 and self._is_retryable_error(e):
                    logger.warning(f"IGDB request failed (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= 2
                continue

            if not isinstance(raw, list):
                raise RuntimeError("Unexpected IGDB response format")

            return raw

        raise RuntimeError(f"IGDB request failed after {self.MAX_RETRIES} attempts: {last_error}") from last_error
    
    
    def _cachear_list(self, query: list[dict]) -> None:
        for r in query:
            try:
                self.cacher.save_game(r)
            except Exception as e:
                logger.warning(f"Failed to cache game {r.get('id')}: {e}")

    
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
            if data:
                return data
            if not self.cacher._available:
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

    
