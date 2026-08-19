"""
Que el log DIGA algo cuando no salen los juegos.

Cada test de aquí cubre un silencio real: situaciones en las que la aplicación
se quedaba sin juegos y no dejaba ni una línea que lo explicara. Lo que se
comprueba no es la redacción, es que **haya** un aviso y que nombre la causa.

Ninguno toca la red: se parchean las peticiones.
"""
import logging

import pytest
import requests

from puntueitor.core import paths
from puntueitor.core.logging_setup import MAX_BYTES, setup_logging


class TestSinSesion:
    """
    Una tienda activa sin sesión iniciada da cero juegos, y eso tiene que
    verse en el arranque. Es el hueco que dejó la ruta de Heroic: antes el
    silencio era "no encuentro la carpeta", ahora sería "no has entrado".
    """

    def test_the_startup_says_which_stores_have_no_session(self, caplog):
        from puntueitor.core.logging_setup import _log_sesiones

        with caplog.at_level(logging.WARNING):
            _log_sesiones(ConfigDoble(gog_is_active=True, epic_is_active=True))

        mensaje = " ".join(r.message for r in caplog.records)
        assert "GOG" in mensaje and "EPIC" in mensaje
        assert "Opciones" in mensaje

    def test_a_store_that_is_off_is_not_reported(self, caplog):
        from puntueitor.core.logging_setup import _log_sesiones

        with caplog.at_level(logging.WARNING):
            _log_sesiones(ConfigDoble(gog_is_active=True))

        mensaje = " ".join(r.message for r in caplog.records)
        assert "GOG" in mensaje and "AMAZON" not in mensaje


class TestSteam:
    def test_without_api_key_it_says_so(self, caplog, monkeypatch):
        """
        Steam activa y sin clave devolvía la tupla vacía sin decir nada: el
        usuario se quedaba sin sus juegos de Steam y sin ninguna pista.
        """
        from puntueitor.core.pipeline import load_steam_library as pipeline

        config = ConfigDoble(steam_api_key="", steam_user_id=123)
        monkeypatch.setattr(pipeline.ConfigManager, "get", property(lambda self: config))

        with caplog.at_level(logging.WARNING):
            list(pipeline.load_library(engine=object()))

        assert any("no hay API key" in r.message for r in caplog.records)

    def test_without_steam_id_it_says_so(self, caplog, monkeypatch):
        from puntueitor.core.pipeline import load_steam_library as pipeline

        config = ConfigDoble(steam_api_key="clave", steam_user_id=0)
        monkeypatch.setattr(pipeline.ConfigManager, "get", property(lambda self: config))

        with caplog.at_level(logging.WARNING):
            list(pipeline.load_library(engine=object()))

        assert any("no hay Steam ID" in r.message for r in caplog.records)

    def test_a_private_profile_is_not_confused_with_an_empty_library(self, caplog, monkeypatch):
        """
        Steam contesta 200 y un `response` VACÍO con el perfil en privado.
        Sin esto era idéntico a "no tienes juegos".
        """
        from steampy.api.steam_api import SteamApi

        api = SteamApi()
        monkeypatch.setattr(api, "_request_json", lambda url, params: {"response": {}})

        with caplog.at_level(logging.WARNING):
            api.owned_games("clave", 123)

        mensaje = " ".join(r.message for r in caplog.records)
        assert "privado" in mensaje and "Steam ID" in mensaje

    def test_a_failed_request_is_logged(self, caplog, monkeypatch):
        """`_request_json` se tragaba TODA excepción y devolvía None."""
        from steampy.api.steam_api import SteamApi

        api = SteamApi()

        def falla(*args, **kwargs):
            raise requests.ConnectionError("Max retries exceeded")

        monkeypatch.setattr(api.session, "get", falla)

        with caplog.at_level(logging.WARNING):
            assert api._request_json("https://api.steampowered.com/x/y/v1/", {}) is None

        assert any("sin conexión a internet" in r.message for r in caplog.records)

    def test_the_api_key_never_reaches_the_log(self, caplog, monkeypatch):
        """La clave viaja en los `params`, y el log se comparte."""
        from steampy.api.steam_api import SteamApi

        api = SteamApi()

        def falla(*args, **kwargs):
            raise requests.ConnectionError("boom")

        monkeypatch.setattr(api.session, "get", falla)

        with caplog.at_level(logging.WARNING):
            api._request_json("https://api.steampowered.com/x/y/v1/", {"key": "SECRETA"})

        assert "SECRETA" not in " ".join(r.message for r in caplog.records)


class ConfigDoble:
    """Lo que `load_library` mira de la configuración."""

    def __init__(self, **kwargs):
        self.steam_is_active = kwargs.get("steam_is_active", True)
        self.gog_is_active = kwargs.get("gog_is_active", False)
        self.epic_is_active = kwargs.get("epic_is_active", False)
        self.amazon_is_active = kwargs.get("amazon_is_active", False)
        self.steam_api_key = kwargs.get("steam_api_key", "")
        self.steam_user_id = kwargs.get("steam_user_id", 0)


class TestIGDB:
    def test_missing_credentials_are_reported_before_going_online(self, monkeypatch):
        """
        Sin credenciales no hay nada que intentar, y el error que devolvía
        IGDB por no mandarlas no se parecía en nada a "te falta ponerlas".
        """
        import igdbpy
        from puntueitor.core.igdb.service import IGDBAuthError, IGDBService

        def no_deberia_llamarse(**kwargs):
            raise AssertionError("no se puede salir a la red sin credenciales")

        monkeypatch.setattr(igdbpy.utils, "generate_api_key", no_deberia_llamarse)

        service = IGDBService(client_id="", client_secret="")
        with pytest.raises(IGDBAuthError, match="faltan las credenciales"):
            service._ensure_token()

    def test_no_internet_is_not_reported_as_bad_credentials(self, monkeypatch):
        """
        La distinción que evita que el usuario toque unas claves que estaban
        bien: las dos cosas eran el mismo `RuntimeError`.
        """
        import igdbpy
        from puntueitor.core.igdb.service import IGDBService, IGDBUnavailableError

        def sin_red(**kwargs):
            raise requests.ConnectionError("Max retries exceeded")

        monkeypatch.setattr(igdbpy.utils, "generate_api_key", sin_red)

        service = IGDBService(client_id="x", client_secret="y")
        with pytest.raises(IGDBUnavailableError, match="sin conexión"):
            service._ensure_token()

    def test_rejected_credentials_say_so(self, monkeypatch):
        import igdbpy
        from puntueitor.core.igdb.service import IGDBAuthError, IGDBService

        response = requests.Response()
        response.status_code = 403

        def rechazado(**kwargs):
            raise requests.HTTPError("403", response=response)

        monkeypatch.setattr(igdbpy.utils, "generate_api_key", rechazado)

        service = IGDBService(client_id="x", client_secret="y")
        with pytest.raises(IGDBAuthError, match="rechazado"):
            service._ensure_token()


class TestSetupLogging:
    def test_writes_where_it_should(self, tmp_path):
        setup_logging("test")
        logging.getLogger("puntueitor.prueba").info("hola")
        logging.shutdown()

        assert "hola" in paths.log_file().read_text()

    def test_it_does_not_truncate_the_previous_session(self, tmp_path):
        """
        Con `filemode="w"` arrancar borraba justo el log que se quería mirar:
        un fallo raro se cuenta a la vuelta, con la aplicación ya reabierta.
        """
        setup_logging("primera")
        logging.getLogger("puntueitor.prueba").info("de la sesión anterior")
        for handler in logging.getLogger().handlers:
            handler.flush()

        setup_logging("segunda")
        logging.getLogger("puntueitor.prueba").info("de la nueva")
        for handler in logging.getLogger().handlers:
            handler.flush()

        contenido = paths.log_file().read_text()
        assert "de la sesión anterior" in contenido
        assert "de la nueva" in contenido

    def test_no_duplicate_handlers(self, tmp_path):
        """Llamarlo dos veces no puede dejar cada línea escrita por duplicado."""
        setup_logging("una")
        setup_logging("otra")
        logging.getLogger("puntueitor.prueba").warning("única")
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert paths.log_file().read_text().count("única") == 1

    def test_noisy_third_parties_are_quiet(self, tmp_path):
        setup_logging("test")
        assert logging.getLogger("urllib3").level == logging.WARNING

    def test_the_header_never_carries_credentials(self, tmp_path, monkeypatch):
        """El log se comparte para pedir ayuda."""
        from puntueitor.core.config import ConfigManager

        config = ConfigManager().get
        config.steam_api_key = "CLAVE-SECRETA"
        config.igdb_client_secret = "SECRETO-IGDB"

        setup_logging("test")
        logging.shutdown()

        contenido = paths.log_file().read_text()
        assert "CLAVE-SECRETA" not in contenido
        assert "SECRETO-IGDB" not in contenido

    def test_it_rotates_instead_of_growing_forever(self, tmp_path):
        setup_logging("test")
        handler = next(
            h for h in logging.getLogger().handlers if hasattr(h, "maxBytes")
        )
        assert handler.maxBytes == MAX_BYTES
        assert handler.backupCount >= 1
