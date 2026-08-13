from puntueitor.core import paths
import json
import logging
import os
import threading
from pathlib import Path
from dataclasses import dataclass, asdict, field, fields

logger = logging.getLogger(__name__)

DEFAULT_MIXED_WEIGHTS = {"critics": 0.3, "users": 0.5, "duration": 0.2}
DEFAULT_WEIGHTED_WEIGHTS = {"critics": 0.4, "users": 0.4, "duration": 0.2}
DEFAULT_AVAILABLE_HOURS = 20.0
DEFAULT_ENABLED_STORES = ["steam"]


def write_json_atomic(path: Path, data: dict) -> None:
    """
    Escribe un JSON de forma que no se pueda quedar a medias.

    Se vuelca a un fichero temporal AL LADO del definitivo y se renombra al
    final con `os.replace`, que es atómico dentro del mismo sistema de
    ficheros. Antes se abría el destino en modo "w", y eso lo TRUNCA en el
    acto: si algo fallaba a mitad (un cierre a destiempo, disco lleno, un
    valor que no se puede serializar) el fichero se quedaba cortado. En
    `config.json` eso significa perder las claves de API. Mismo criterio que
    ya se usa para las carátulas en `gui3d/covers.py`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _from_dict(cls, data: dict):
    """Instancia `cls` quedándose solo con las claves que conoce."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Config:
    steam_api_key: str = ""
    steam_user_id: int = 0
    igdb_client_id: str = ""
    igdb_client_secret: str = ""

    steam_is_active: bool = True
    gog_is_active: bool = False
    epic_is_active: bool = False
    amazon_is_active: bool = False
    heroic_path: str = ""


@dataclass
class ScoringConfig:
    """
    Ajustes de los sistemas de puntuación, en su propio fichero
    (`paths.scoring_file()`).

    Los nombres de los campos conservan el prefijo `scoring_` que tenían
    cuando vivían en `config.json`, aunque aquí sea redundante: así los que
    ya los leían (`LibraryService`, las dos pantallas de configuración) no
    cambian de expresión, y la migración es una copia literal de claves.
    """

    scoring_mixed_critics: float = DEFAULT_MIXED_WEIGHTS["critics"]
    scoring_mixed_users: float = DEFAULT_MIXED_WEIGHTS["users"]
    scoring_mixed_duration: float = DEFAULT_MIXED_WEIGHTS["duration"]

    scoring_weighted_critics: float = DEFAULT_WEIGHTED_WEIGHTS["critics"]
    scoring_weighted_users: float = DEFAULT_WEIGHTED_WEIGHTS["users"]
    scoring_weighted_duration: float = DEFAULT_WEIGHTED_WEIGHTS["duration"]

    scoring_available_hours: float = DEFAULT_AVAILABLE_HOURS
    scoring_preferred_genres: list[str] = field(default_factory=list)


#: Claves de scoring que pudieron quedar en un `config.json` antiguo.
_SCORING_KEYS = tuple(f.name for f in fields(ScoringConfig))


def load_scoring() -> ScoringConfig:
    """
    Lee los ajustes de scoring, migrando desde `config.json` si hace falta.

    La primera vez que se ejecuta con un `config.json` de los de antes (con
    las claves `scoring_*` dentro), se vuelcan a `scoring.json` y se limpian
    del original. El orden importa: primero se ESCRIBE el fichero nuevo y
    solo después se toca el viejo, así que una interrupción entre medias
    deja los valores duplicados —inofensivo, `Config` ignora las claves que
    no conoce— y nunca perdidos.
    """
    path = paths.scoring_file()
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return _from_dict(ScoringConfig, json.load(f))
        except (json.JSONDecodeError, OSError) as error:
            logger.error(f"Error leyendo {path}: {error}; se usan los valores por defecto")
            return ScoringConfig()

    legacy = _read_json(paths.config_file())
    scoring = _from_dict(ScoringConfig, legacy)
    save_scoring(scoring)

    if any(key in legacy for key in _SCORING_KEYS):
        logger.info(f"Ajustes de scoring migrados a {path}")
        _strip_scoring_from_config(legacy)

    return scoring


def save_scoring(scoring: ScoringConfig) -> None:
    write_json_atomic(paths.scoring_file(), asdict(scoring))


def _read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        return {}


def _strip_scoring_from_config(data: dict) -> None:
    """Quita las claves de scoring del `config.json` ya migrado."""
    limpio = {k: v for k, v in data.items() if k not in _SCORING_KEYS}
    if limpio != data:
        write_json_atomic(paths.config_file(), limpio)

class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ConfigManager, cls).__new__(cls)
                    cls._instance._load()
        return cls._instance

    def __init__(self):
        # Initialization happens in _load during __new__
        pass

    def _load(self):
        self.config_dir = paths.config_dir()
        self.config_file = paths.config_file()

        if not self.config_file.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.config = Config()
            self.save()
            logger.info(f"Created new config file: {self.config_file}")
        else:
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info(f"Loaded config data: {data.keys()}")

                # Filter fields that exist in Config dataclass
                config_field_names = {f.name for f in fields(Config)}
                config_data = {k: v for k, v in data.items() if k in config_field_names}

                self.config = Config(**config_data)
                logger.info(f"Config loaded: steam_is_active={self.config.steam_is_active}, gog_is_active={self.config.gog_is_active}, epic_is_active={self.config.epic_is_active}, amazon_is_active={self.config.amazon_is_active}")
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Error loading config: {e}")
                self.config = Config()

    def save(self):
        """
        Guarda la configuración. Atómico: este fichero lleva las claves de
        API y no puede quedarse a medias (ver `write_json_atomic`).

        Se conservan las claves que haya en disco y no conozca `Config` — un
        `scoring_*` que quedara de antes de la migración, por ejemplo —, en
        vez de tirarlas al reescribir: guardar la configuración no debería
        borrar datos de nadie más.
        """
        data = _read_json(self.config_file)
        data.update(asdict(self.config))
        write_json_atomic(self.config_file, data)
        logger.info(f"Config saved: {self.config_file}")

    @property
    def get(self) -> Config:
        return self.config
