"""
Traducir un fallo a una frase que se entienda.

Lo que se fija aquí no es la redacción exacta —eso cambiará— sino las
distinciones que importan: sin internet NO es lo mismo que la clave no vale,
y eso es justo lo que el log no distinguía.
"""
import socket

import pytest
import requests

from puntueitor.core.diagnostics import (
    describe_error,
    is_auth_error,
    is_offline,
    missing_credentials,
    status_code,
)


def _http_error(estado: int) -> requests.HTTPError:
    """Un error de `requests` con su respuesta, como el de `raise_for_status`."""
    response = requests.Response()
    response.status_code = estado
    return requests.HTTPError(f"{estado} Error", response=response)


class TestSinInternet:
    @pytest.mark.parametrize("error", [
        requests.ConnectionError("HTTPSConnectionPool: Max retries exceeded"),
        socket.gaierror("[Errno -3] Temporary failure in name resolution"),
        ConnectionRefusedError("Connection refused"),
        # De `igdbpy`, que envuelve el fallo y solo deja la frase: por eso hay
        # que mirar el texto además del tipo.
        RuntimeError("Name or service not known"),
    ])
    def test_recognised(self, error):
        assert is_offline(error)
        assert "sin conexión a internet" in describe_error(error, "IGDB")

    def test_names_who_could_not_be_reached(self):
        assert "IGDB" in describe_error(requests.ConnectionError("boom"), "IGDB")


class TestCredenciales:
    @pytest.mark.parametrize("estado", [401, 403])
    def test_says_they_are_the_problem(self, estado):
        mensaje = describe_error(_http_error(estado), "Steam")

        assert is_auth_error(_http_error(estado))
        assert "credenciales" in mensaje
        # Y dónde se arregla: sin esto el usuario sabe qué pasa pero no qué
        # hacer, que es la mitad del trabajo. Cuentas, no Tiendas: las claves
        # están ahí desde que se separaron las dos pantallas.
        assert "Cuentas" in mensaje

    def test_a_500_is_not_a_credentials_problem(self):
        """
        La distinción que más importa: mandar al usuario a revisar sus claves
        cuando lo que pasa es que el servicio está caído le hace perder el
        rato y, peor, tocar unas claves que estaban bien.
        """
        mensaje = describe_error(_http_error(500), "IGDB")
        assert "credenciales" not in mensaje
        assert not is_auth_error(_http_error(500))


class TestOtrosEstados:
    def test_rate_limit(self):
        assert "limitando" in describe_error(_http_error(429), "IGDB")

    @pytest.mark.parametrize("estado", [500, 502, 503, 504])
    def test_server_errors(self, estado):
        mensaje = describe_error(_http_error(estado), "IGDB")
        assert f"HTTP {estado}" in mensaje

    def test_unknown_status_still_says_the_number(self):
        assert "HTTP 418" in describe_error(_http_error(418), "IGDB")

    def test_status_code_without_response(self):
        assert status_code(ValueError("nada")) is None


class TestTimeout:
    def test_recognised(self):
        error = requests.Timeout("HTTPSConnectionPool: Read timed out")
        assert "no respondió a tiempo" in describe_error(error, "HowLongToBeat")

    def test_it_is_not_reported_as_no_internet(self):
        """Que tarden en contestar no es no tener red, y se arregla distinto."""
        error = requests.Timeout("Read timed out")
        assert "sin conexión" not in describe_error(error)


class TestLoDemas:
    def test_keeps_the_message(self):
        assert "algo raro" in describe_error(ValueError("algo raro"))

    def test_an_empty_error_still_says_something(self):
        """Nunca se devuelve una frase vacía: quedaría un log mudo."""
        mensaje = describe_error(ValueError(""))
        assert "ValueError" in mensaje

    def test_no_service_no_problem(self):
        assert describe_error(ValueError("x")).strip()


class _Config:
    def __init__(self, **kwargs):
        self.steam_is_active = kwargs.get("steam_is_active", True)
        self.steam_api_key = kwargs.get("steam_api_key", "")
        self.steam_user_id = kwargs.get("steam_user_id", 0)
        self.igdb_client_id = kwargs.get("igdb_client_id", "")
        self.igdb_client_secret = kwargs.get("igdb_client_secret", "")


class TestCredencialesQueFaltan:
    def test_lists_them_by_name(self):
        faltan = missing_credentials(_Config())
        assert faltan == [
            "API key de Steam", "Steam ID",
            "Client ID de IGDB", "Client Secret de IGDB",
        ]

    def test_never_leaks_a_value(self):
        """
        El log se comparte para pedir ayuda: aquí solo pueden salir NOMBRES.
        """
        config = _Config(
            steam_api_key="CLAVE-SECRETA", steam_user_id=123,
            igdb_client_id="ID-SECRETO", igdb_client_secret="",
        )
        texto = " ".join(missing_credentials(config))
        assert "CLAVE-SECRETA" not in texto
        assert "ID-SECRETO" not in texto

    def test_a_disabled_store_is_not_nagged_about(self):
        """Quien no use Steam no tiene por qué ver esto en cada arranque."""
        config = _Config(
            steam_is_active=False,
            igdb_client_id="x", igdb_client_secret="y",
        )
        assert missing_credentials(config) == []

    def test_nothing_missing(self):
        config = _Config(
            steam_api_key="k", steam_user_id=1,
            igdb_client_id="x", igdb_client_secret="y",
        )
        assert missing_credentials(config) == []
