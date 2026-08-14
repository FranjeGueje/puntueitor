"""
Actualizar la biblioteca sin destruir nada.

Lo importante aquí no es lo que hace, sino lo que NO hace: la variante suave
—la única que usa el carrusel— tiene que dejar intactos los resolvers, la
caché de IGDB, los extras, los desconocidos y los estados del usuario. Perder
cualquiera de esos significa horas de red para reconstruirlos, o directamente
datos que no se pueden recuperar (los terminados y los favoritos).

`load_library` va monkeypatcheado en todos: ningún test toca la red.
"""
import pytest

from puntueitor.core.models import Library
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.services.library_refresh import refresh_library


@pytest.fixture
def repo(tmp_path) -> LibraryRepository:
    return LibraryRepository(cache_dir=tmp_path)


@pytest.fixture
def poblado(repo, make_game):
    """Un repositorio con algo que perder en cada una de sus tablas."""
    repo.resolvers_cacher.set_igdb_ids("steam", "12345", [1])
    repo.igdb_cacher.save_game({"id": 1, "name": "Ya Estaba"})
    repo.save_game(make_game(igdb_id=1, duration_hours=10.0))
    repo.library_cacher.set_status(
        1, finished=True, hidden=False, backlog=False, favorite=True,
    )
    repo.unknown_cacher.save_unknown("epic", "Algo Raro", "abc")
    return repo


@pytest.fixture
def falso_pipeline(monkeypatch):
    """Sustituye `load_library` y deja ver con qué se le llamó."""
    llamadas = {}

    def fake(**kwargs):
        llamadas.update(kwargs)
        return iter(llamadas.pop("_games", []))

    def emite(*games):
        llamadas["_games"] = list(games)

    # En su módulo de origen: `refresh_library` lo importa dentro de la
    # función, así que cuando corre el test todavía no hay ningún nombre al
    # que apuntar en `library_refresh`.
    import puntueitor.core.pipeline.load_steam_library as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "load_library", fake)
    fake.llamadas = llamadas
    fake.emite = emite
    return fake


@pytest.fixture(autouse=True)
def sin_enrichers(monkeypatch):
    """Los enrichers van a la red al construirse; fuera."""
    import puntueitor.core.enrichers.hltb_enricher as hltb_mod
    import puntueitor.core.enrichers.steam_score_enricher as steam_mod
    import puntueitor.core.igdb.service as igdb_mod
    import puntueitor.core.resolvers.hltb_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "HLTBResolver", lambda *a, **k: object())
    monkeypatch.setattr(hltb_mod, "HLTBEnricher", lambda **k: object())
    monkeypatch.setattr(steam_mod, "SteamScoreEnricher", lambda **k: object())
    monkeypatch.setattr(igdb_mod.IGDBService, "__init__", lambda self, *a, **k: None)


class TestNoDestruye:
    def test_keeps_everything(self, poblado, falso_pipeline, make_game):
        falso_pipeline.emite(make_game(igdb_id=2, title="Nuevo"))

        refresh_library(poblado)

        assert poblado.resolvers_cacher.get_stores_for_igdb_id(1) == {"steam": "12345"}
        assert poblado.igdb_cacher.get_game(1) is not None
        assert poblado.extras_cacher.get_extras(1)["duration_hours"] == 10.0
        assert poblado.unknown_cacher.is_unknown("epic", "abc")
        estados = poblado.library_cacher.get_all_statuses()[1]
        assert estados["finished"] and estados["favorite"]


class TestParametros:
    def test_soft_by_default(self, repo, falso_pipeline):
        """
        `refresh=False` es lo que evita volver a pedir a IGDB lo cacheado;
        `force_store_refresh=True` es lo que hace que se vean los juegos
        comprados desde la última vez.
        """
        refresh_library(repo)
        assert falso_pipeline.llamadas["refresh"] is False
        assert falso_pipeline.llamadas["force_store_refresh"] is True

    def test_callbacks_are_passed_through(self, repo, falso_pipeline):
        def progreso(*a): ...
        def enriquecido(*a): ...

        refresh_library(repo, on_progress=progreso, on_enriched=enriquecido)

        assert falso_pipeline.llamadas["progress_callback"] is progreso
        assert falso_pipeline.llamadas["enrichment_callback"] is enriquecido


class TestEmision:
    def test_reports_every_game(self, repo, falso_pipeline, make_game):
        juegos = [make_game(igdb_id=i, title=f"J{i}") for i in (1, 2, 3)]
        falso_pipeline.emite(*juegos)
        vistos = []

        total = refresh_library(repo, on_game=vistos.append)

        assert total == 3
        assert [g.igdb_id for g in vistos] == [1, 2, 3]

    def test_saves_extras_as_it_goes(self, repo, falso_pipeline, make_game):
        """
        Se guarda sobre la marcha, no solo al final: esto dura minutos y
        cortarlo a medias no debe tirar lo ya averiguado.
        """
        guardados = []
        falso_pipeline.emite(
            make_game(igdb_id=1, duration_hours=5.0),
            make_game(igdb_id=2, duration_hours=None),
        )

        refresh_library(repo, on_game=lambda g: guardados.append(
            repo.extras_cacher.get_extras(1).get("duration_hours"),
        ))

        # Ya estaba guardado cuando llegó el primer aviso.
        assert guardados[0] == 5.0

    def test_empty_library(self, repo, falso_pipeline):
        falso_pipeline.emite()
        assert refresh_library(repo) == 0
        assert len(repo.load()) == 0


def test_library_is_saved_at_the_end(repo, falso_pipeline, make_game, monkeypatch):
    guardadas = []
    monkeypatch.setattr(
        LibraryRepository, "save", lambda self, lib: guardadas.append(list(lib)),
    )
    falso_pipeline.emite(make_game(igdb_id=1), make_game(igdb_id=2))

    refresh_library(repo)

    assert len(guardadas) == 1
    assert [g.igdb_id for g in guardadas[0]] == [1, 2]
    assert isinstance(Library.from_iterable(guardadas[0]), Library)
