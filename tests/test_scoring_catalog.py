"""
Los sistemas de puntuación se describen en un solo sitio.

Los textos estaban escritos dos veces —en la TUI y en el carrusel— y ya
habían divergido: la TUI tenía frases y una recomendación final que el
carrusel no enseñaba. El módulo del carrusel lo documentaba como mal
necesario ("importar el de la TUI metería Textual entero"), y tenía razón en
el diagnóstico: la solución era sacar los textos de las interfaces, no
copiarlos.
"""
import pytest

from puntueitor.core.config import load_scoring
from puntueitor.core.scoring import catalog


class TestElCatalogoEstaCompleto:
    def test_every_system_has_its_texts(self):
        for sistema in catalog.SYSTEMS:
            assert sistema.name, sistema.key
            assert sistema.title, sistema.key
            assert sistema.description, sistema.key
            assert sistema.recommendation, sistema.key

    def test_every_system_knows_how_to_build_its_scorer(self):
        config = load_scoring()

        for sistema in catalog.SYSTEMS:
            scorer = sistema.build(config)
            assert hasattr(scorer, "score"), sistema.key

    def test_every_system_declares_its_config_form(self):
        formularios = {"weights", "hours", "genres"}

        for sistema in catalog.SYSTEMS:
            assert sistema.config_form in formularios, sistema.key

    def test_the_keys_are_the_ones_the_service_understands(self):
        """
        Se guardan en la configuración del usuario: cambiarlas rompería sus
        ajustes.
        """
        assert {s.key for s in catalog.SYSTEMS} == {
            "mixed", "weighted", "time", "genre",
        }

    def test_keys_are_unique(self):
        claves = [s.key for s in catalog.SYSTEMS]
        assert len(set(claves)) == len(claves)

    def test_an_unknown_system_is_not_invented(self):
        assert catalog.get("no-existe") is None


class TestLasDosInterfacesDicenLoMismo:
    """
    El test que hace imposible la divergencia que motivó todo esto.
    """

    def test_the_titles_match(self):
        from puntueitor.gui3d import scoring_info
        from puntueitor.tui.screens.scoring import SCORING_INFO

        for sistema in catalog.SYSTEMS:
            assert SCORING_INFO[sistema.key]["title"] == sistema.title
            assert scoring_info.BY_KEY[sistema.key].title == sistema.title

    def test_the_descriptions_match(self):
        from puntueitor.gui3d import scoring_info
        from puntueitor.tui.screens.scoring import SCORING_INFO

        for sistema in catalog.SYSTEMS:
            assert (
                SCORING_INFO[sistema.key]["desc"]
                == scoring_info.description_for(sistema.key)
            ), sistema.key

    def test_both_show_the_same_systems_in_the_same_order(self):
        from puntueitor.gui3d import scoring_info
        from puntueitor.tui.screens.scoring import SCORING_INFO

        assert list(SCORING_INFO) == [s.key for s in scoring_info.SCORERS]

    def test_neither_writes_its_own_texts(self):
        """
        El guardián: que nadie vuelva a pegar las descripciones en un módulo
        de interfaz. Se reconoce por los apodos, que son lo más característico
        de estos textos.
        """
        from pathlib import Path

        raiz = Path(__file__).resolve().parent.parent
        apodos = ("Recomendador Inteligente", "Equilibrado", "Planificador",
                  "Personalizador")

        culpables = []
        for fichero in (raiz / "puntueitor").rglob("*.py"):
            if "__pycache__" in fichero.parts:
                continue
            if fichero.name == "catalog.py":
                continue
            texto = fichero.read_text()
            if any(apodo in texto for apodo in apodos):
                culpables.append(str(fichero.relative_to(raiz)))

        assert not culpables, (
            "escriben los textos de scoring en vez de usar el catálogo: "
            + ", ".join(culpables)
        )


class TestLaRecomendacion:
    def test_the_carousel_shows_it_too(self):
        """
        Era lo único que solo tenía la TUI. Va en un campo aparte —no es otra
        versión de la descripción— así que las dos pueden enseñarla.
        """
        from puntueitor.gui3d import scoring_info

        for sistema in catalog.SYSTEMS:
            assert sistema.recommendation in scoring_info.description_for(sistema.key)

    def test_it_is_not_part_of_the_description(self):
        """Si se colara dentro, volveríamos a tener un solo texto que crece."""
        for sistema in catalog.SYSTEMS:
            assert sistema.recommendation not in sistema.description
