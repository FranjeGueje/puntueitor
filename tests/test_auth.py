"""
Sesiones de tienda: guardar el token, renovarlo y leer lo que se pega.

Ninguna prueba toca la red: las peticiones se sustituyen por dobles. Lo que
se comprueba es la política —cuándo se renueva, cuándo se da por caducada,
qué se acepta al pegar—, no las URLs de cada tienda, que son suyas y pueden
cambiar sin que esto tenga nada que decir.
"""
import time

import pytest

from puntueitor.core.auth.errors import AuthError, NotLoggedIn, SessionExpired
from puntueitor.core.auth.oauth import OAuthSession
from puntueitor.core.auth.paste import extract_code
from puntueitor.core.auth.token_store import TokenStore


class TestTokenStore:
    def test_saves_and_reads(self):
        store = TokenStore("gog")
        store.save({"access_token": "abc", "refresh_token": "def", "expires_in": 3600})

        assert TokenStore("gog").access_token == "abc"
        assert TokenStore("gog").refresh_token == "def"

    def test_expires_in_becomes_an_absolute_moment(self):
        """
        Un plazo relativo dentro de un fichero que sobrevive al reinicio no
        significa nada: al volver mañana, "caduca en una hora" daría por
        bueno un token muerto hace doce.
        """
        store = TokenStore("gog")
        store.save({"access_token": "abc", "expires_in": 3600})

        assert store.data["expires_at"] > time.time()
        assert "expires_in" not in store.data

    def test_a_token_without_expiry_is_treated_as_expired(self):
        store = TokenStore("gog")
        store.save({"access_token": "abc"})

        assert store.is_expired()

    def test_it_expires_before_the_deadline(self):
        """
        Con margen: que caduque a mitad de una carga de mil juegos deja media
        biblioteca sin traer.
        """
        store = TokenStore("gog")
        store.save({"access_token": "abc", "expires_in": 60})

        assert store.is_expired()
        assert not store.is_expired(margin=0)

    def test_the_file_is_only_readable_by_its_owner(self):
        store = TokenStore("gog")
        store.save({"access_token": "abc"})

        assert store.path.stat().st_mode & 0o077 == 0

    def test_an_unreadable_file_does_not_raise(self):
        store = TokenStore("gog")
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("{esto no es json")

        assert store.data == {}
        assert not store.has_session()

    def test_clear_forgets_everything(self):
        store = TokenStore("gog")
        store.save({"access_token": "abc"})
        store.clear()

        assert not TokenStore("gog").has_session()


class SesionDoble(OAuthSession):
    STORE = "gog"
    LABEL = "Tienda"

    def __init__(self, respuesta=None, error=None, **kwargs):
        super().__init__(**kwargs)
        self.respuesta = respuesta or {"access_token": "nuevo", "expires_in": 3600}
        self.error = error
        self.renovaciones = 0

    def login_url(self):
        return "https://ejemplo/login"

    def _exchange(self, code):
        return {**self.respuesta, "code_usado": code}

    def _renew(self, refresh_token):
        self.renovaciones += 1
        if self.error:
            raise self.error
        return {**self.respuesta, "refresh_token": refresh_token}


class TestOAuthSession:
    def test_without_session_it_says_to_log_in(self):
        with pytest.raises(NotLoggedIn):
            SesionDoble().access_token()

    def test_a_valid_token_is_not_renewed(self):
        sesion = SesionDoble()
        sesion.tokens.save({"access_token": "vale", "expires_in": 3600})

        assert sesion.access_token() == "vale"
        assert sesion.renovaciones == 0

    def test_an_expired_token_is_renewed(self):
        sesion = SesionDoble()
        sesion.tokens.save({
            "access_token": "viejo", "refresh_token": "r", "expires_in": 1,
        })

        assert sesion.access_token() == "nuevo"
        assert sesion.renovaciones == 1

    def test_expired_without_refresh_token_asks_to_log_in_again(self):
        sesion = SesionDoble()
        sesion.tokens.save({"access_token": "viejo", "expires_in": 1})

        with pytest.raises(SessionExpired):
            sesion.access_token()

    def test_a_network_failure_renewing_is_not_an_expired_session(self):
        """
        Si un corte de internet se tomara por sesión caducada, un rato sin
        conexión obligaría a iniciar sesión otra vez en las tres tiendas.
        """
        sesion = SesionDoble(error=OSError("sin red"))
        sesion.tokens.save({
            "access_token": "viejo", "refresh_token": "r", "expires_in": 1,
        })

        with pytest.raises(AuthError) as fallo:
            sesion.access_token()
        assert not isinstance(fallo.value, SessionExpired)

    def test_a_login_with_nothing_recognizable_is_rejected(self):
        with pytest.raises(AuthError, match="no se reconoce"):
            SesionDoble().complete_login("esto no es un código de nada")

    def test_logout_forgets_the_session(self):
        sesion = SesionDoble()
        sesion.tokens.save({"access_token": "abc"})
        sesion.logout()

        assert not sesion.is_logged_in()


class TestLoQueSePega:
    """
    Se acepta la URL entera, el JSON de Epic o el código pelado. Obligar a
    encontrar un parámetro dentro de una URL de cuatrocientos caracteres es
    el paso donde se pierde a la gente.
    """

    def test_a_whole_url(self):
        pegado = "https://embed.gog.com/on_login_success?origin=client&code=ABC123"
        assert extract_code(pegado, ("code",)) == "ABC123"

    def test_a_url_with_the_parameters_after_the_hash(self):
        assert extract_code("https://x/y#code=ABC123&state=1", ("code",)) == "ABC123"

    def test_the_json_that_epic_shows(self):
        pegado = '{"redirectUrl": "https://x", "authorizationCode": "EPIC1"}'
        assert extract_code(pegado, ("authorizationCode", "code")) == "EPIC1"

    def test_a_bare_code(self):
        assert extract_code("  ABC123  ", ("code",)) == "ABC123"

    def test_quotes_around_it(self):
        assert extract_code('"ABC123"', ("code",)) == "ABC123"

    def test_half_a_sentence_is_not_a_code(self):
        assert extract_code("no lo he encontrado", ("code",)) == ""

    def test_nothing(self):
        assert extract_code("", ("code",)) == ""

    def test_a_url_without_the_parameter(self):
        assert extract_code("https://x/y?state=1", ("code",)) == ""

    def test_the_order_of_the_names_matters(self):
        pegado = "https://x?code=segundo&authorizationCode=primero"
        assert extract_code(pegado, ("authorizationCode", "code")) == "primero"
