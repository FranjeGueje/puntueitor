"""
Lo que cada proveedor hace con la respuesta de su tienda.

Sin red: se le pasa un cliente HTTP de mentira. No se comprueban las URLs
—son de las tiendas y pueden cambiar mañana—, sino lo que sí es nuestro:
qué se filtra, cómo se pagina y con qué claves sale, que es lo que los
resolvers esperan encontrar.
"""
from puntueitor.core.providers.amazon import AmazonProvider
from puntueitor.core.providers.epic import EpicProvider
from puntueitor.core.providers.gog import GOGProvider
from puntueitor.core.providers.itchio import (
    MAX_PAGINAS,
    POR_PAGINA,
    ItchioProvider,
)
from puntueitor.core.providers.steam import SteamProvider


class RespuestaDoble:
    def __init__(self, datos):
        self._datos = datos

    def raise_for_status(self):
        pass

    def json(self):
        return self._datos


class HttpDoble:
    """Devuelve respuestas de una cola, y apunta lo que se le pidió."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []

    def get(self, url, **kwargs):
        self.peticiones.append((url, kwargs))
        return RespuestaDoble(self.respuestas.pop(0))

    post = get


class SesionDoble:
    def __init__(self, serial="SERIAL"):
        self.device_serial = serial

    def is_logged_in(self):
        return True

    def bearer_headers(self):
        return {"Authorization": "Bearer x"}

    def access_token(self):
        return "x"


class TestGOG:
    def test_the_id_and_the_title_come_out_where_the_resolver_looks(self):
        http = HttpDoble({
            "totalPages": 1,
            "products": [{"id": 1207658893, "title": "Baldur's Gate 2"}],
        })
        provider = GOGProvider(session=SesionDoble(), http=http)

        juegos = provider.fetch(refresh=True)

        assert juegos[0]["app_name"] == "1207658893"
        assert juegos[0]["title"] == "Baldur's Gate 2"

    def test_it_goes_through_every_page(self):
        http = HttpDoble(
            {"totalPages": 2, "products": [{"id": 1, "title": "Uno"}]},
            {"totalPages": 2, "products": [{"id": 2, "title": "Dos"}]},
        )
        provider = GOGProvider(session=SesionDoble(), http=http)

        juegos = provider.fetch(refresh=True)

        assert [j["title"] for j in juegos] == ["Uno", "Dos"]
        assert len(http.peticiones) == 2

    def test_it_does_not_ask_for_pages_that_are_not_there(self):
        http = HttpDoble({"totalPages": 1, "products": [{"id": 1, "title": "Uno"}]})
        GOGProvider(session=SesionDoble(), http=http).fetch(refresh=True)

        assert len(http.peticiones) == 1


class TestEpic:
    def test_a_game_comes_out_with_its_title_and_its_store_url(self):
        assets = [{"appName": "Batfish", "namespace": "ns", "catalogItemId": "cid"}]
        ficha = {"cid": {
            "title": "Telltale Batman",
            "productSlug": "batman/home",
            "categories": [{"path": "games"}],
        }}
        provider = EpicProvider(session=SesionDoble(), http=HttpDoble(assets, ficha))

        juegos = provider.fetch(refresh=True)

        assert juegos[0]["app_name"] == "Batfish"
        assert juegos[0]["title"] == "Telltale Batman"
        # Sin el "/home" que Epic arrastra en los slugs antiguos: el resolver
        # busca en IGDB por ese trozo y con la barra dentro no encuentra nada.
        assert juegos[0]["store_url"].endswith("/batman")

    def test_the_unreal_marketplace_is_left_out(self):
        """Ahí hay plugins de desarrollo, no juegos que nadie vaya a jugar."""
        assets = [{"appName": "Plugin", "namespace": "ue", "catalogItemId": "cid"}]
        provider = EpicProvider(session=SesionDoble(), http=HttpDoble(assets))

        assert list(provider.fetch(refresh=True)) == []

    def test_dlcs_and_applications_come_through(self):
        """
        Paridad con la v2, que leía la caché de Heroic y sí los traía (497
        entradas, 41 marcadas como DLC). Filtrarlos aquí los hacía
        desaparecer sin dejar rastro: ni carrusel ni Desconocidos. Quien
        decide si algo es identificable es el resolver.
        """
        assets = [{"appName": "DLC", "namespace": "ns", "catalogItemId": "cid"}]
        ficha = {"cid": {
            "title": "Expansión",
            "mainGameItem": {"id": "otro"},
            "categories": [{"path": "addons"}],
        }}
        provider = EpicProvider(session=SesionDoble(), http=HttpDoble(assets, ficha))

        juegos = provider.fetch(refresh=True)

        assert [j["title"] for j in juegos] == ["Expansión"]

    def test_a_game_whose_catalog_entry_fails_does_not_sink_the_rest(self):
        """Son cientos de peticiones; perder una no puede tirar el refresco."""
        class HttpQueFalla(HttpDoble):
            def get(self, url, **kwargs):
                if "catalog" in url:
                    raise OSError("boom")
                return super().get(url, **kwargs)

        assets = [
            {"appName": "A", "namespace": "ns", "catalogItemId": "c1"},
            {"appName": "B", "namespace": "ns", "catalogItemId": "c2"},
        ]
        provider = EpicProvider(
            session=SesionDoble(), http=HttpQueFalla(assets),
        )

        assert list(provider.fetch(refresh=True)) == []


class TestAmazon:
    def test_the_release_date_is_kept_where_its_resolver_looks(self):
        """
        Amazon no tiene ningún id que IGDB conozca: la fecha es lo único que
        distingue un remaster de su original al buscar por título.
        """
        respuesta = {"entitlements": [{"product": {
            "id": "c7827e1e",
            "title": "Samurai Shodown V Special",
            "releaseDate": "2020-01-01T00:00:00Z",
        }}]}
        provider = AmazonProvider(
            session=SesionDoble(), http=HttpDoble(respuesta),
        )

        juegos = provider.fetch(refresh=True)

        assert juegos[0]["app_name"] == "c7827e1e"
        assert juegos[0]["extra"]["releaseDate"] == "2020-01-01T00:00:00Z"

    def test_it_follows_the_next_token(self):
        http = HttpDoble(
            {"entitlements": [{"product": {"id": "1", "title": "Uno"}}],
             "nextToken": "sigue"},
            {"entitlements": [{"product": {"id": "2", "title": "Dos"}}]},
        )
        provider = AmazonProvider(session=SesionDoble(), http=http)

        juegos = provider.fetch(refresh=True)

        assert [j["title"] for j in juegos] == ["Uno", "Dos"]

    def test_an_entitlement_without_a_product_is_skipped(self):
        respuesta = {"entitlements": [{"nada": 1}, {"product": {"id": "1", "title": "Uno"}}]}
        provider = AmazonProvider(session=SesionDoble(), http=HttpDoble(respuesta))

        assert len(provider.fetch(refresh=True)) == 1

    def test_without_a_device_serial_it_does_not_even_try(self):
        """
        Amazon no da tokens a aplicaciones, registra dispositivos: sin el
        serial con el que se registró, la petición no se puede ni firmar.
        """
        provider = AmazonProvider(session=SesionDoble(serial=""))

        listo, motivo = provider.is_ready()
        assert not listo and "Cuentas" in motivo


class TestSteamProvider:
    def test_without_credentials_it_says_which_one_is_missing(self):
        listo, motivo = SteamProvider(api_key="", user_id=1).is_ready()
        assert not listo and "API key" in motivo

        listo, motivo = SteamProvider(api_key="k", user_id=0).is_ready()
        assert not listo and "Steam ID" in motivo

    def test_the_appid_is_the_identifier(self):
        assert SteamProvider.store_id({"appid": 400, "name": "Portal"}) == "400"
        assert SteamProvider.store_title({"appid": 400, "name": "Portal"}) == "Portal"


class CacherDoble:
    """Un `StoreLibraryCacher` de mentira con lo de la vez anterior."""

    def __init__(self, guardados=None):
        self._guardados = guardados
        self.escrituras = []

    def get_games(self):
        return self._guardados

    def save_games(self, juegos, id_of, title_of):
        self.escrituras.append(list(juegos))


class TestEpicNoRepitePreguntas:
    """
    Epic obliga a una petición por juego para saber su título, y eso eran
    ~450 peticiones en cada recarga. Pero título, enlace y `catalog_item_id`
    no cambian: son la ficha pública del juego. Reutilizar lo ya guardado
    deja la recarga en una petición más los juegos nuevos.
    """

    ASSET = {"appName": "Batfish", "namespace": "ns", "catalogItemId": "cid"}
    CACHEADA = {
        "app_name": "Batfish", "title": "Telltale Batman",
        "store_url": "https://x/batman", "namespace": "ns",
        "catalog_item_id": "cid",
    }

    def test_a_known_game_is_not_asked_for_again(self):
        http = HttpDoble([self.ASSET])       # solo contesta a los assets
        provider = EpicProvider(
            session=SesionDoble(), http=http,
            cacher=CacherDoble([self.CACHEADA]),
        )

        juegos = provider.fetch(refresh=True)

        assert juegos == [self.CACHEADA]
        assert len(http.peticiones) == 1, "no debía consultar el catálogo"

    def test_a_new_game_is_asked_for(self):
        nuevo = {"appName": "Otro", "namespace": "ns", "catalogItemId": "c2"}
        ficha = {"c2": {"title": "Otro juego", "productSlug": "otro"}}
        http = HttpDoble([self.ASSET, nuevo], ficha)
        provider = EpicProvider(
            session=SesionDoble(), http=http,
            cacher=CacherDoble([self.CACHEADA]),
        )

        titulos = [j["title"] for j in provider.fetch(refresh=True)]

        assert sorted(titulos) == ["Otro juego", "Telltale Batman"]
        assert len(http.peticiones) == 2, "solo el catálogo del nuevo"

    def test_a_changed_catalog_id_is_asked_for_again(self):
        """Si Epic le cambia la ficha al juego, la caché ya no vale."""
        cambiado = {"appName": "Batfish", "namespace": "ns", "catalogItemId": "OTRO"}
        ficha = {"OTRO": {"title": "Telltale Batman Remasterizado"}}
        http = HttpDoble([cambiado], ficha)
        provider = EpicProvider(
            session=SesionDoble(), http=http,
            cacher=CacherDoble([self.CACHEADA]),
        )

        juegos = provider.fetch(refresh=True)

        assert juegos[0]["title"] == "Telltale Batman Remasterizado"

    def test_a_failed_lookup_falls_back_to_what_was_known(self):
        """
        Sin esto, una ficha que falla borra el juego de la biblioteca Y de la
        caché, porque `save_games` reemplaza la tienda entera.
        """
        cambiado = {"appName": "Batfish", "namespace": "ns", "catalogItemId": "OTRO"}

        class HttpQueFallaElCatalogo(HttpDoble):
            def get(self, url, **kwargs):
                if "catalog" in url:
                    raise OSError("boom")
                return super().get(url, **kwargs)

        provider = EpicProvider(
            session=SesionDoble(), http=HttpQueFallaElCatalogo([cambiado]),
            cacher=CacherDoble([self.CACHEADA]),
        )

        assert provider.fetch(refresh=True) == [self.CACHEADA]

    def test_the_failures_are_reported(self, caplog):
        import logging

        nuevo = {"appName": "Nuevo", "namespace": "ns", "catalogItemId": "c9"}

        class HttpQueFallaElCatalogo(HttpDoble):
            def get(self, url, **kwargs):
                if "catalog" in url:
                    raise OSError("boom")
                return super().get(url, **kwargs)

        provider = EpicProvider(
            session=SesionDoble(), http=HttpQueFallaElCatalogo([nuevo]),
            cacher=CacherDoble([]),
        )

        with caplog.at_level(logging.WARNING):
            provider.fetch(refresh=True)

        assert any("no se pudieron consultar" in r.message for r in caplog.records)


class TestItchio:
    """
    La única tienda de las cinco con API oficial y documentada.

    Lo que se prueba aquí es cómo se para de paginar: `owned-keys` no dice
    cuántas páginas hay —a diferencia de GOG—, así que el proveedor tiene que
    deducirlo, y equivocarse ahí significa o media biblioteca o un bucle sin
    fin.
    """

    @staticmethod
    def _clave(id_juego, titulo):
        return {"game": {"id": id_juego, "title": titulo, "url": f"https://x/{titulo}"}}

    def test_the_id_and_the_title_come_out_where_the_resolver_looks(self):
        http = HttpDoble({"owned_keys": [self._clave(583923, "Celeste Classic")]})
        provider = ItchioProvider(session=SesionDoble(), http=http)

        juegos = provider.fetch(refresh=True)

        # `app_name` es el mismo id numérico que IGDB indexa como `uid` de su
        # fuente externa "Itchio": el resolver lo busca tal cual.
        assert juegos[0]["app_name"] == "583923"
        assert juegos[0]["title"] == "Celeste Classic"

    def test_a_page_that_is_not_full_is_the_last_one(self):
        http = HttpDoble({"owned_keys": [self._clave(1, "Uno")]})
        ItchioProvider(session=SesionDoble(), http=http).fetch(refresh=True)

        assert len(http.peticiones) == 1

    def test_it_keeps_asking_while_the_pages_come_full(self):
        llenas = [self._clave(n, f"J{n}") for n in range(POR_PAGINA)]
        http = HttpDoble({"owned_keys": llenas}, {"owned_keys": [self._clave(99, "Fin")]})
        provider = ItchioProvider(session=SesionDoble(), http=http)

        juegos = provider.fetch(refresh=True)

        assert len(juegos) == POR_PAGINA + 1
        assert [p[1]["params"]["page"] for p in http.peticiones] == [1, 2]

    def test_an_empty_page_also_stops_it(self):
        """
        Una página llena justa de la que no hay siguiente: itch.io contesta
        con la lista vacía y ahí se acaba, sin pedir la tercera.
        """
        llenas = [self._clave(n, f"J{n}") for n in range(POR_PAGINA)]
        http = HttpDoble({"owned_keys": llenas}, {"owned_keys": []})
        provider = ItchioProvider(session=SesionDoble(), http=http)

        assert len(provider.fetch(refresh=True)) == POR_PAGINA
        assert len(http.peticiones) == 2

    def test_a_key_without_its_game_is_left_out(self):
        """
        Se compran también cosas que no son juegos (packs, bundles): vienen
        sin `game` y colarlas rompería al normalizar.
        """
        http = HttpDoble({"owned_keys": [{"id": 1}, self._clave(2, "Sí")]})
        provider = ItchioProvider(session=SesionDoble(), http=http)

        assert [j["title"] for j in provider.fetch(refresh=True)] == ["Sí"]

    def test_it_does_not_spin_forever(self, caplog):
        """
        Si itch.io contestara siempre con páginas llenas, el tope corta y deja
        aviso: mejor media biblioteca que un refresco que no termina nunca.
        """
        llenas = [self._clave(n, f"J{n}") for n in range(POR_PAGINA)]

        class HttpSinFin(HttpDoble):
            def get(self, url, **kwargs):
                self.peticiones.append((url, kwargs))
                return RespuestaDoble({"owned_keys": llenas})

        http = HttpSinFin()
        provider = ItchioProvider(session=SesionDoble(), http=http)

        with caplog.at_level("WARNING"):
            juegos = provider.fetch(refresh=True)

        assert len(http.peticiones) == MAX_PAGINAS
        assert len(juegos) == MAX_PAGINAS * POR_PAGINA
        assert "puede faltar parte de la biblioteca" in caplog.text
