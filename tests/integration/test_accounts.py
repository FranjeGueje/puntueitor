"""
El servicio de cuentas, que es lo que llaman las dos interfaces.

En `integration` porque escribe de verdad el token y la configuración, aquí
dentro del sandbox de `conftest`. No abre ningún navegador: `webbrowser` se
sustituye.
"""
import pytest

from puntueitor.core.auth.token_store import TokenStore
from puntueitor.core.config import ConfigManager
from puntueitor.core.services import accounts


@pytest.fixture(autouse=True)
def sin_navegador(monkeypatch):
    abiertas = []
    monkeypatch.setattr(
        accounts.webbrowser, "open", lambda url: abiertas.append(url) or True,
    )
    return abiertas


class TestAbrirLogin:
    @pytest.mark.parametrize("store", ["steam", "gog", "epic", "amazon"])
    def test_every_store_has_a_login_page(self, store, sin_navegador):
        resultado = accounts.open_login(store)

        assert resultado.ok
        assert sin_navegador[0].startswith("https://")

    def test_without_a_browser_the_address_is_handed_over(self, monkeypatch):
        """
        Por SSH o en el modo juego del Deck no hay navegador que abrir, y
        quedarse sin poder iniciar sesión por eso sería absurdo.
        """
        monkeypatch.setattr(accounts.webbrowser, "open", lambda url: False)

        resultado = accounts.open_login("gog")

        assert resultado.ok
        assert resultado.url.startswith("https://")


class TestTerminarLogin:
    def test_nothing_pasted(self):
        assert not accounts.finish_login("gog", "   ").ok

    def test_something_unrecognizable_says_what_to_paste(self):
        resultado = accounts.finish_login("gog", "no lo encuentro")

        assert not resultado.ok
        assert "pegad" in resultado.mensaje.lower() or "pega" in resultado.mensaje.lower()

    def test_a_failure_is_returned_not_raised(self, monkeypatch):
        """
        Como el resto de `core/services`: esto se llama desde hilos de la
        interfaz, y una excepción cruzando esa frontera es un cierre en seco.
        """
        class SesionQueRevienta:
            def complete_login(self, pegado):
                raise RuntimeError("boom")

        monkeypatch.setattr(accounts, "_sesion", lambda store: SesionQueRevienta())

        resultado = accounts.finish_login("gog", "ABC123")

        assert not resultado.ok
        assert "boom" in resultado.mensaje


class TestSteam:
    def test_the_openid_answer_becomes_the_configured_steam_id(self):
        pegado = (
            "https://steamcommunity.com/?openid.claimed_id="
            "https%3A%2F%2Fsteamcommunity.com%2Fopenid%2Fid%2F76561198000000000"
        )

        assert accounts.finish_login("steam", pegado).ok
        assert ConfigManager().get.steam_user_id == 76561198000000000

    def test_a_vanity_url_is_rejected(self):
        resultado = accounts.finish_login(
            "steam", "https://steamcommunity.com/id/mi-nombre",
        )

        assert not resultado.ok
        assert "17 cifras" in resultado.mensaje

    def test_logging_out_forgets_the_steam_id(self):
        manager = ConfigManager()
        manager.get.steam_user_id = 76561198000000000
        manager.save()

        assert accounts.logout("steam").ok
        assert ConfigManager().get.steam_user_id == 0


class TestEstado:
    def test_a_store_with_a_token_shows_as_logged_in(self):
        TokenStore("gog").save({"access_token": "abc"})

        assert accounts.has_session("gog")
        assert accounts.sessions_summary()["gog"]

    def test_steam_needs_the_key_and_the_id_both(self):
        manager = ConfigManager()
        manager.get.steam_api_key = "clave"
        manager.get.steam_user_id = 0
        manager.save()

        assert not accounts.has_session("steam")

        manager.get.steam_user_id = 76561198000000000
        manager.save()

        assert accounts.has_session("steam")

    def test_logging_out_leaves_it_without_a_session(self):
        TokenStore("gog").save({"access_token": "abc"})
        accounts.logout("gog")

        assert not accounts.has_session("gog")
