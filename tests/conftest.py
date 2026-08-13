"""
Fixtures comunes y, sobre todo, el aislamiento de la suite.

El orden de este fichero es deliberado: el sandbox se monta ARRIBA DEL TODO,
antes de importar nada de `puntueitor`. Un fixture, por muy `autouse` que
sea, solo corre cuando ya empieza un test — para entonces los módulos ya se
han importado, y si alguno tocara el disco al importarse (lo hacía
`core/paths.py`, que migraba ficheros del `$HOME` real) el daño ya estaría
hecho. Aislar en el import es la única forma de cubrir esa ventana.
"""
import os
import tempfile
from datetime import date
from collections.abc import Callable
from pathlib import Path

# ─── SANDBOX: antes de cualquier import de `puntueitor` ──────────────────
#
# Se parchean las DOS vías por las que `core/paths.py` resuelve rutas, y
# hacen falta las dos:
#   - Las XDG_*: es lo que mira primero para los directorios base.
#   - `Path.home`: el respaldo cuando no hay XDG... y también lo que usa
#     `_legacy_moves()` para el ORIGEN de las rutas antiguas, que por
#     definición son pre-XDG. Parchear solo las variables dejaría los
#     orígenes apuntando al `$HOME` de verdad, que es exactamente cómo se
#     llegó a mover ficheros reales del usuario a un directorio temporal.
_SANDBOX = Path(tempfile.mkdtemp(prefix="puntueitor-tests-"))

for _variable, _sub in (
    ("XDG_CONFIG_HOME", "config"),
    ("XDG_DATA_HOME", "data"),
    ("XDG_CACHE_HOME", "cache"),
    ("XDG_STATE_HOME", "state"),
):
    os.environ[_variable] = str(_SANDBOX / _sub)

Path.home = staticmethod(lambda: _SANDBOX)
# ─────────────────────────────────────────────────────────────────────────

import pytest

from puntueitor.core import paths
from puntueitor.core.config import ConfigManager
from puntueitor.core.models import Game, Library, Stores, ScoringContext, SelectionContext


def pytest_configure(config):
    """
    Comprueba que el sandbox está puesto ANTES de correr ningún test.

    Si alguien reordena los imports de este fichero y el sandbox deja de
    montarse a tiempo, es preferible que la suite no arranque a que empiece
    a escribir en los ficheros del usuario.
    """
    real_home = Path(os.path.expanduser("~"))
    for ruta in (paths.config_file(), paths.data_dir(), paths.cache_dir(),
                 paths.state_dir()):
        assert not str(ruta).startswith(str(real_home)), (
            f"AISLAMIENTO ROTO: {ruta} apunta al home real. "
            "No se ejecuta la suite para no tocar los ficheros del usuario."
        )


@pytest.fixture(autouse=True)
def isolate_user_files(tmp_path, monkeypatch):
    """
    Da a CADA test su propio directorio limpio, encima del sandbox global.

    El sandbox de arriba ya garantiza que nada sale del temporal; esto es lo
    que además evita que un test vea los ficheros que dejó el anterior. Un
    aislamiento que hubiera que recordar poner test a test falla por
    omisión; éste falla por seguro.

    Se BORRAN las variables XDG y se parchea `Path.home` a `tmp_path`. El
    borrado es seguro precisamente porque `Path.home` queda apuntando a un
    temporal: hay una sola fuente de la verdad (`tmp_path`) y coincide con lo
    que dan por hecho los tests que escriben a mano en `tmp_path/".config"`.

    Se reinicia además el singleton de `ConfigManager`, que si no se quedaría
    con el directorio del primer test que lo instanciara.

    OJO al usar `monkeypatch` dentro de un test: `monkeypatch.undo()` deshace
    TODO lo parcheado, esto incluido. Como el sandbox global de arriba NO es
    un monkeypatch, deshacerlo ya no devuelve al `$HOME` real — pero sí
    mezcla los ficheros de ese test con los de otros. Para revertir un solo
    parche está `with monkeypatch.context() as m:`.
    """
    for variable in (
        "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

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
