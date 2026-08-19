import json
import logging
import requests
import time
import threading

from puntueitor.core.diagnostics import describe_error

logger = logging.getLogger(__name__)


class SteamApi:
    # -----------------------------
    # Constructor
    # -----------------------------
    def __init__(
        self,
        timeout: int = 5,
        user_agent: str = "steampy/0.1",
        rate_limit: int = 5,      # peticiones
        rate_period: float = 1.0, # segundos
    ):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.rate_limit = rate_limit
        self.rate_period = rate_period
        self._request_times: list[float] = []
        self._rate_lock = threading.Lock()

    # -----------------------------
    # Helpers privados
    # -----------------------------
    def _request_json(self, url: str, params: dict) -> dict | None:
        """
        Realiza una petición GET y devuelve JSON o None.

        El None se queda —quien llama ya cuenta con él— pero DEJANDO DICHO por
        qué. Antes esto se tragaba toda excepción en silencio, así que no tener
        internet, tener la API key mal o que Steam estuviera caído acababan
        exactamente igual: cero juegos y ni una línea en el log que lo
        explicara.

        La URL se registra sin `params` a propósito: ahí dentro va la API key.
        """
        self._rate_limit_wait()
        endpoint = url.rstrip("/").rsplit("/", 2)[-2:][0]
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            logger.warning(f"[{endpoint}] {describe_error(error, 'Steam')}")
            return None
        except json.JSONDecodeError as error:
            logger.warning(
                f"Steam ({endpoint}) devolvió una respuesta ilegible: {error}"
            )
            return None

    def _rate_limit_wait(self):
        """Aplica rate limiting simple basado en ventana temporal."""
        if self.rate_limit <= 0:
            return
        now = time.monotonic()
        with self._rate_lock:
            self._request_times = [t for t in self._request_times if now - t < self.rate_period]
            if len(self._request_times) >= self.rate_limit:
                sleep_time = self.rate_period - (now - self._request_times[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
            self._request_times.append(time.monotonic())

    # -----------------------------
    # Helpers públicos
    # -----------------------------
    @staticmethod
    def get_reviews(data: dict) -> dict:
        """Extrae resumen de reseñas y calcula porcentaje positivo."""
        summary = data.get("query_summary", {})
        total = summary.get("total_reviews", 0)
        positive = summary.get("total_positive", 0)
        return {
            "total_reviews": total,
            "total_positive": positive,
            "total_negative": summary.get("total_negative", 0),
            "review_score_desc": summary.get("review_score_desc") or "",
            "positive_percent": round(positive / total * 100, 2) if total > 0 else 0,
        }

    # -----------------------------
    # APIs Steam
    # -----------------------------

    #📈 Estadísticas de jugadores concurrentes
    def number_of_players(self, appid: int) -> int:
        url = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
        data = self._request_json(url, {"json": 1, "appid": appid})
        return data.get("response", {}).get("player_count", 0) if data else 0

    #🧩 Logros y estadísticas del juego (requiere APIKEY)
    def schema_for_game(self, key: str, appid: int) -> dict | None:
        url = "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
        data = self._request_json(url, {"json": 1, "key": key, "appid": appid})
        return data.get("game") if data else None

    #🏆 Porcentaje global de logros (requiere APIKEY)
    def global_achievement_for_app(self, key: str, appid: int) -> list[dict] | None:
        url = "https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/"
        data = self._request_json(url, {"json": 1, "key": key, "gameid": appid})
        return data.get("achievementpercentages", {}).get("achievements") if data else None

    #👤 Información pública de un usuario (requiere APIKEY)
    def player_summaries(self, key: str, steamids: int) -> dict | None:
        url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
        data = self._request_json(url, {"json": 1, "key": key, "steamids": steamids})
        players = data.get("response", {}).get("players", []) if data else []
        return players[0] if players else None

    #🎮 Juegos de un usuario (requiere APIKEY)
    def owned_games(
        self,
        key: str,
        steamid: int,
        include_appinfo: bool = True,
        include_played_free_games: bool = True,
    ) -> list[dict] | None:
        """
        Juegos en propiedad de un usuario.

        Sin caché: de guardarla se encarga `SteamProvider`, en la misma base
        que las otras tres tiendas. Aquí solo se habla con Steam.

        Devuelve None si la petición falló —el porqué ya está en el log— y
        lista vacía si Steam contestó pero sin juegos. Son dos casos
        distintos: el primero se arregla solo cuando vuelva la red, y el
        segundo es de configuración.
        """
        url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
        params = {
            "json": 1,
            "key": key,
            "steamid": steamid,
            "include_appinfo": include_appinfo,
            "include_played_free_games": include_played_free_games,
        }

        data = self._request_json(url, params)
        if not data:
            # El porqué ya lo ha registrado `_request_json`.
            return None

        entry = data.get("response", {}).get("games")
        if not entry:
            # Steam contesta 200 y un `response` VACÍO cuando no tiene nada
            # que enseñarnos. Sin esto era indistinguible de "no tienes
            # juegos", que es lo que parecía.
            #
            # El orden de las causas importa, porque es lo que la gente lee
            # cuando se queda sin juegos. La privacidad va la ÚLTIMA: según
            # la documentación de Steamworks no aplica cuando la API key
            # pertenece a la misma cuenta que se consulta, que es el caso
            # normal aquí. Lo más probable es que la clave y el ID no sean
            # de la misma cuenta.
            logger.warning(
                f"Steam no devolvió ningún juego para el usuario {steamid}: "
                "comprueba que el Steam ID es correcto y que la API key es de "
                "ESA misma cuenta. Si la clave es de otra cuenta, además "
                "tendrías que tener el perfil (y los detalles de juego) en "
                "público. Revísalo en Opciones → Cuentas"
            )
            return []

        return entry
