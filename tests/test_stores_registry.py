"""
El registro de tiendas: la única lista de qué tiendas hay.

Antes, ese mismo hecho vivía en once ficheros —colores, etiquetas, banderas
de configuración, tablas de resolvers— sincronizados a mano, y eso ya falló
dos veces: filas de menú que se pintaban pero no hacían nada al elegirlas, y
una tienda colándose en una lista de la que debía estar fuera.

Lo que se prueba aquí no es que las cuatro tiendas de hoy estén bien, sino
que **el registro es de verdad la única fuente**: que nada quede sin declarar,
y que una tienda nueva aparezca sola en todas partes.
"""
from dataclasses import fields

import pytest

from puntueitor.core import stores
from puntueitor.core.config import Config
from puntueitor.core.models import Stores
from puntueitor.core.stores.spec import StoreSpec


class TestNadaSeQuedaSinDeclarar:
    def test_every_registered_store_is_in_the_enum(self):
        """La clave del enum es con la que se guardan sus juegos."""
        for spec in stores.all_stores():
            assert spec.store in Stores

    def test_every_store_in_the_enum_is_registered(self):
        """
        El olvido al revés, que es el que no se ve: añadir el miembro del
        enum y no registrar la tienda la dejaría invisible en los menús sin
        que fallara nada.
        """
        registradas = {spec.store for spec in stores.all_stores()}
        assert registradas == set(Stores)

    def test_every_store_has_its_config_flag(self):
        """
        Es una de las dos líneas que siguen fuera del módulo de la tienda.
        Si falta, la tienda no se podría activar nunca.
        """
        campos = {f.name for f in fields(Config)}
        for spec in stores.all_stores():
            assert spec.config_flag in campos, spec.label

    def test_every_store_has_a_provider_and_a_resolver(self):
        for spec in stores.all_stores():
            assert callable(spec.provider), spec.label
            assert spec.resolver() is not None, spec.label

    def test_stores_with_a_session_declare_how_to_build_it(self):
        for spec in stores.with_session():
            assert callable(spec.session), spec.label
            assert spec.paste_hint, f"{spec.label}: hay que decir qué pegar"

    def test_keys_and_labels_are_unique(self):
        claves = [spec.key for spec in stores.all_stores()]
        etiquetas = [spec.label for spec in stores.all_stores()]
        assert len(set(claves)) == len(claves)
        assert len(set(etiquetas)) == len(etiquetas)


class TestSteamEsLaExcepcion:
    def test_steam_declares_it_has_no_session(self):
        """
        No tiene OAuth para terceros. Que lo diga su propio módulo —y no una
        lista aparte de "tiendas con sesión"— es lo que evita que alguien
        recorra el enum entero y le pinte un botón de conectar.
        """
        assert not stores.get(Stores.STEAM).has_session
        assert Stores.STEAM not in [s.store for s in stores.with_session()]

    def test_the_others_do_have_one(self):
        assert {s.key for s in stores.with_session()} == {"gog", "epic", "amazon"}


class TestActivas:
    def test_only_the_ones_marked_in_the_config(self):
        config = Config(steam_is_active=True, gog_is_active=True,
                        epic_is_active=False, amazon_is_active=False)

        assert [s.key for s in stores.active(config)] == ["steam", "gog"]

    def test_the_order_is_the_one_of_the_registry(self):
        """
        El orden manda en dos sitios: cómo se pintan en los menús y qué color
        gana cuando un juego está en varias tiendas.
        """
        config = Config(steam_is_active=True, gog_is_active=True,
                        epic_is_active=True, amazon_is_active=True)
        orden = [s.key for s in stores.active(config)]

        assert orden == [s.key for s in stores.all_stores()]


class TestBuscar:
    def test_by_enum_or_by_text(self):
        assert stores.get(Stores.GOG) is stores.get("gog")

    def test_something_that_is_not_a_store(self):
        assert stores.find("itch") is None

    def test_get_raises_for_the_unknown(self):
        with pytest.raises((KeyError, ValueError)):
            stores.get("itch")


class TestUnaTiendaNueva:
    """
    La prueba que justifica todo el trabajo: registrar una tienda de mentira
    y comprobar que aparece SOLA en todo lo que antes había que tocar a mano.
    """

    @pytest.fixture
    def playstation(self, monkeypatch):
        falsa = StoreSpec(
            # Se reutiliza un miembro del enum porque el enum no se puede
            # ampliar en caliente; lo que se prueba es el registro, no el enum.
            store=Stores.AMAZON,
            label="PlayStation",
            config_flag="amazon_is_active",
            color=(0.0, 0.3, 0.9),
            provider=lambda config: "proveedor",
            resolver=lambda: str,
            session=lambda: "sesión",
            paste_hint="Pega lo que te dé PlayStation",
        )
        registro = tuple(
            falsa if spec.store == Stores.AMAZON else spec
            for spec in stores.REGISTRY
        )
        monkeypatch.setattr(stores, "REGISTRY", registro)
        monkeypatch.setattr(
            stores, "_POR_TIENDA", {s.store: s for s in registro},
        )
        return falsa

    def test_it_shows_up_in_the_carousel_menus(self, playstation):
        from puntueitor.gui3d import menus

        # Se reconstruyen: son tuplas calculadas al importar.
        tiendas = tuple(
            (s.config_flag, s.label) for s in stores.all_stores()
        )
        cuentas = tuple((s.key, s.label) for s in stores.with_session())

        assert ("amazon_is_active", "PlayStation") in tiendas
        assert ("amazon", "PlayStation") in cuentas

    def test_it_brings_its_own_colour(self, playstation):
        colores = {s.store: s.color for s in stores.all_stores()}

        assert colores[Stores.AMAZON] == (0.0, 0.3, 0.9)

    def test_it_is_built_when_it_is_active(self, playstation):
        from puntueitor.core.providers import build_providers

        config = Config(steam_is_active=False, gog_is_active=False,
                        epic_is_active=False, amazon_is_active=True)

        assert build_providers(config) == {Stores.AMAZON: "proveedor"}

    def test_its_session_is_reachable_by_name(self, playstation):
        from puntueitor.core.services import accounts

        assert accounts._sesion("amazon") == "sesión"


class TestNoVuelvenLasTablasParalelas:
    """
    Que nadie escriba otra lista de las cuatro tiendas por su cuenta.

    Es el fallo que este registro viene a arreglar, y el que más fácil se
    cuela otra vez: alguien necesita "las tiendas" en un módulo nuevo, escribe
    la lista a mano, y a partir de ahí hay dos verdades. Esto lo caza leyendo
    el código, igual que `tests/test_indicaciones.py` con los avisos.
    """

    #: Módulos donde SÍ puede estar la lista: el registro y sus tiendas.
    PERMITIDOS = ("core/stores/",)

    @staticmethod
    def _fuentes():
        from pathlib import Path

        raiz = Path(__file__).resolve().parent.parent
        for fichero in (raiz / "puntueitor").rglob("*.py"):
            if "__pycache__" in fichero.parts:
                continue
            yield fichero.relative_to(raiz), fichero.read_text()

    def test_nobody_lists_the_four_stores_by_hand(self):
        culpables = []
        for ruta, texto in self._fuentes():
            if any(p in str(ruta) for p in self.PERMITIDOS):
                continue
            for numero, linea in enumerate(texto.splitlines(), 1):
                # Sin comentarios: la prosa nombra tiendas a menudo y con
                # razón ("Steam, GOG..." como ejemplo), y eso no es una tabla.
                linea = linea.split("#", 1)[0]
                # Dos o más tiendas nombradas en la misma línea de CÓDIGO es
                # señal de tabla escrita a mano. Una sola puede ser legítima
                # (Steam tiene su propio proveedor, por ejemplo).
                nombradas = sum(
                    1 for clave in ("steam", "gog", "epic", "amazon")
                    if f'"{clave}"' in linea.lower() or f"'{clave}'" in linea.lower()
                )
                if nombradas >= 2:
                    culpables.append(f"{ruta}:{numero}")

        assert not culpables, (
            "estas líneas listan tiendas a mano en vez de usar el registro: "
            + ", ".join(culpables)
        )

    def test_the_enum_is_not_walked_where_the_registry_should_be(self):
        """
        Recorrer `Stores` entero fue lo que coló a Steam en la lista de
        tiendas con sesión. Quien quiera "todas las tiendas" tiene que pedir
        `stores.all_stores()`, que además trae el orden bueno.
        """
        culpables = [
            f"{ruta}:{numero}"
            for ruta, texto in self._fuentes()
            if not any(p in str(ruta) for p in self.PERMITIDOS)
            for numero, linea in enumerate(texto.splitlines(), 1)
            if "for store in Stores" in linea or "in set(Stores)" in linea
        ]

        assert not culpables, (
            "recorren el enum en vez del registro: " + ", ".join(culpables)
        )
