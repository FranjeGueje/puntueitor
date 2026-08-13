from datetime import date
from collections.abc import Callable
from pathlib import Path

import pytest

from puntueitor.core.config import ConfigManager
from puntueitor.core.models import Game, Library, Stores, ScoringContext, SelectionContext


@pytest.fixture(autouse=True)
def isolate_user_files(tmp_path, monkeypatch):
    """
    Ningún test toca los ficheros reales del usuario. Se aplica a TODOS.

    No es paranoia: esta suite ya llegó a sobrescribir el `config.json` real
    y a dejar un juego inventado en la `library.sqlite` real, porque bastaba
    con que un test llamara a algo que por dentro construyera su ruta por
    defecto. Un aislamiento por test (recordar parchear `Path.home` en cada
    uno) falla por omisión; este falla por seguro.

    Se BORRAN las variables XDG en vez de apuntarlas al temporal, y luego se
    parchea `Path.home`. Así queda una sola fuente de la verdad: `paths.py`
    mira primero las XDG y solo cae a `Path.home()` si no están, de modo que
    apuntarlas a otro sitio dejaría los ficheros en un directorio distinto
    del que dan por hecho los tests que escriben a mano en
    `tmp_path/".config"`.

    Se reinicia además el singleton de `ConfigManager`, que si no se quedaría
    con el directorio del primer test que lo instanciara.

    OJO al usar `monkeypatch` dentro de un test: `monkeypatch.undo()` deshace
    TODO lo parcheado, esto incluido, y deja al test hablando con los
    ficheros de verdad. Para deshacer solo un parche concreto está
    `with monkeypatch.context() as m:`.
    """
    for variable in (
        "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    ConfigManager._instance = None
    yield
    ConfigManager._instance = None


@pytest.fixture
def make_game() -> Callable[..., Game]:
    def _make_game(**overrides) -> Game:
        defaults = dict(
            igdb_id=1,
            title="Test Game",
            genres=("Action", "Adventure"),
            storyline="A test game for testing",
            release_date=date(2020, 6, 15),
            cover_url="https://images.igdb.com/cover.jpg",
            critic_score=80.0,
            user_score=75.0,
            duration_hours=20.0,
            steam_review=7,
            steamdb_score=77.73,
            review_pos=1000,
            review_neg=100,
            finished=False,
            hidden=False,
            backlog=False,
            favorite=False,
        )
        defaults.update(overrides)
        return Game(**defaults)
    return _make_game


@pytest.fixture
def sample_game(make_game) -> Game:
    return make_game()


@pytest.fixture
def sample_games(make_game) -> list[Game]:
    return [
        make_game(
            igdb_id=1,
            title="Zelda Breath of the Wild",
            genres=("Action", "Adventure"),
            critic_score=97.0,
            user_score=85.0,
            duration_hours=50.0,
            finished=False,
            hidden=False,
            backlog=True,
            favorite=True,
            steamdb_score=95.0,
        ),
        make_game(
            igdb_id=2,
            title="Elden Ring",
            genres=("RPG", "Action"),
            critic_score=96.0,
            user_score=78.0,
            duration_hours=60.0,
            finished=True,
            hidden=False,
            backlog=False,
            favorite=False,
            steamdb_score=92.0,
        ),
        make_game(
            igdb_id=3,
            title="Stardew Valley",
            genres=("Simulation", "RPG"),
            critic_score=89.0,
            user_score=90.0,
            duration_hours=100.0,
            finished=True,
            hidden=True,
            backlog=False,
            favorite=False,
            steamdb_score=88.0,
        ),
        make_game(
            igdb_id=4,
            title="Portal 2",
            genres=("Puzzle",),
            critic_score=95.0,
            user_score=92.0,
            duration_hours=8.0,
            finished=False,
            hidden=False,
            backlog=False,
            favorite=True,
            steamdb_score=94.0,
        ),
        make_game(
            igdb_id=5,
            title="Unknown Game",
            genres=(),
            critic_score=None,
            user_score=None,
            duration_hours=None,
            finished=False,
            hidden=False,
            backlog=False,
            favorite=False,
            steamdb_score=None,
        ),
    ]


@pytest.fixture
def sample_library(sample_games) -> Library:
    return Library.from_iterable(sample_games)


@pytest.fixture
def empty_library() -> Library:
    return Library.from_iterable(())


@pytest.fixture
def scoring_context() -> ScoringContext:
    return ScoringContext(
        available_hours=20.0,
        preferred_genres={"Action"},
        disliked_genres={"Horror"},
        duration_scale=80.0,
        neutral_duration_score=0.5,
        ideal_duration=15.0,
        max_duration=60.0,
    )


@pytest.fixture
def selection_context() -> SelectionContext:
    return SelectionContext(
        title="Test Game",
        source=None,
        release_year=2020,
        steam_appid="12345",
    )
