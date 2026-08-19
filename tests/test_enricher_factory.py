"""
Los enrichers se construyen en un solo sitio.

Se construían en SEIS, con argumentos ligeramente distintos, y cinco de ellos
se olvidaban de pasarle a `SteamScoreEnricher` dónde guardar. O sea que las
notas de Steam solo se persistían al recargar la biblioteca; enriquecer un
juego suelto, rescatar un desconocido o actualizar los extras las volvían a
pedir en cada pasada.

No fue un descuido: es lo que pasa con seis construcciones del mismo par. El
arreglo no es añadir el argumento cinco veces, es que solo haya una forma de
construirlos.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class TestNadieLosConstruyePorSuCuenta:
    """
    El guardián. Sin esto, el séptimo sitio que alguien añada volverá a
    olvidarse de algún cacher, igual que se olvidaron los seis primeros.
    """

    #: Dónde SÍ se pueden construir: la fábrica y los propios enrichers.
    PERMITIDOS = ("core/enrichers/",)

    CONSTRUCCION = re.compile(r"\b(HLTBEnricher|SteamScoreEnricher)\s*\(")

    @staticmethod
    def _fuentes():
        for fichero in (RAIZ / "puntueitor").rglob("*.py"):
            if "__pycache__" in fichero.parts:
                continue
            yield fichero.relative_to(RAIZ), fichero.read_text()

    def test_they_are_only_built_in_the_factory(self):
        culpables = [
            f"{ruta}:{numero}"
            for ruta, texto in self._fuentes()
            if not any(p in str(ruta) for p in self.PERMITIDOS)
            for numero, linea in enumerate(texto.splitlines(), 1)
            if self.CONSTRUCCION.search(linea.split("#", 1)[0])
        ]

        assert not culpables, (
            "construyen enrichers a mano en vez de usar la fábrica: "
            + ", ".join(culpables)
        )


class TestTodosLlevanSusCachers:
    """
    El fallo concreto: `SteamScoreEnricher` se construía en seis sitios y
    cinco no le pasaban `extras_cacher`, así que sus notas solo se guardaban
    al recargar la biblioteca.
    """

    @staticmethod
    def _repo(tmp_path):
        from puntueitor.core.repository.library_repository import LibraryRepository

        return LibraryRepository()

    def test_every_enricher_gets_where_to_save(self, tmp_path):
        from puntueitor.core.enrichers.factory import build_enrichers

        for enricher in build_enrichers(self._repo(tmp_path)):
            assert enricher.extras_cacher is not None, type(enricher).__name__

    def test_also_when_overwriting(self, tmp_path):
        """
        `overwrite=True` es lo que usan "enriquecer DESTRUCTIVO" y actualizar
        los extras — dos de los caminos que se olvidaban del cacher.
        """
        from puntueitor.core.enrichers.factory import build_enrichers

        enrichers = build_enrichers(self._repo(tmp_path), overwrite=True)

        assert enrichers, "tiene que devolver alguno"
        for enricher in enrichers:
            assert enricher.extras_cacher is not None, type(enricher).__name__
            assert enricher.overwrite is True

    def test_by_default_it_does_not_overwrite(self, tmp_path):
        from puntueitor.core.enrichers.factory import build_enrichers

        for enricher in build_enrichers(self._repo(tmp_path)):
            assert enricher.overwrite is False


class TestResistencia:
    """
    Que uno falle al prepararse no puede dejar sin enriquecer a los demás.
    Esa red la tenía solo `refresh_library`; los otros cinco sitios se
    habrían quedado sin nada porque reventara el que no toca.
    """

    def test_one_that_explodes_does_not_take_the_others(self, monkeypatch, caplog):
        import logging

        from puntueitor.core.enrichers import factory
        from puntueitor.core.repository.library_repository import LibraryRepository

        import puntueitor.core.resolvers.hltb_resolver as hltb_mod

        def revienta(*a, **k):
            raise RuntimeError("HowLongToBeat no está")

        monkeypatch.setattr(hltb_mod, "HLTBResolver", revienta)

        with caplog.at_level(logging.WARNING):
            enrichers = factory.build_enrichers(LibraryRepository())

        assert len(enrichers) == 1, "el de Steam tenía que sobrevivir"
        assert any("HLTB" in r.message for r in caplog.records)


class TestAplicarEnCadena:
    def test_it_passes_the_game_through_all_of_them(self):
        from dataclasses import replace

        from puntueitor.core.enrichers.factory import apply_enrichers

        class Suma:
            def __init__(self, cuanto):
                self.cuanto = cuanto

            def enrich(self, game):
                return replace(game, duration_hours=(game.duration_hours or 0) + self.cuanto)

        from puntueitor.core.models import Game

        resultado = apply_enrichers(
            Game(igdb_id=1, title="X"), [Suma(2), Suma(3)],
        )

        assert resultado.duration_hours == 5

    def test_without_enrichers_the_game_comes_back_untouched(self):
        from puntueitor.core.enrichers.factory import apply_enrichers
        from puntueitor.core.models import Game

        juego = Game(igdb_id=1, title="X")

        assert apply_enrichers(juego, []) is juego
