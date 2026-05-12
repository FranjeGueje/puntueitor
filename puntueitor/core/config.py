import json
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)

DEFAULT_MIXED_WEIGHTS = {"critics": 0.3, "users": 0.5, "duration": 0.2}
DEFAULT_WEIGHTED_WEIGHTS = {"critics": 0.4, "users": 0.4, "duration": 0.2}
DEFAULT_AVAILABLE_HOURS = 20.0
DEFAULT_ENABLED_STORES = ["steam"]


@dataclass
class Config:
    steam_api_key: str = ""
    steam_user_id: int = 0
    igdb_client_id: str = ""
    igdb_client_secret: str = ""

    scoring_mixed_critics: float = DEFAULT_MIXED_WEIGHTS["critics"]
    scoring_mixed_users: float = DEFAULT_MIXED_WEIGHTS["users"]
    scoring_mixed_duration: float = DEFAULT_MIXED_WEIGHTS["duration"]

    scoring_weighted_critics: float = DEFAULT_WEIGHTED_WEIGHTS["critics"]
    scoring_weighted_users: float = DEFAULT_WEIGHTED_WEIGHTS["users"]
    scoring_weighted_duration: float = DEFAULT_WEIGHTED_WEIGHTS["duration"]

    scoring_available_hours: float = DEFAULT_AVAILABLE_HOURS
    scoring_preferred_genres: list[str] = field(default_factory=list)

    steam_is_active: bool = True
    heroic_is_active: bool = False
    gog_is_active: bool = False
    epic_is_active: bool = False
    amazon_is_active: bool = False
    heroic_path: str = ""

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
        self.config_dir = Path.home() / ".config" / "puntueitor"
        self.config_file = self.config_dir / "config.json"

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
                config_data = {k: v for k, v in data.items() if hasattr(Config, k)}

                self.config = Config(**config_data)
                logger.info(f"Config loaded: steam_is_active={self.config.steam_is_active}, gog_is_active={self.config.gog_is_active}, epic_is_active={self.config.epic_is_active}, amazon_is_active={self.config.amazon_is_active}")
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Error loading config: {e}")
                self.config = Config()

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        config_dict = asdict(self.config)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=4)
        logger.info(f"Config saved: {config_dict}")

    @property
    def get(self) -> Config:
        return self.config
