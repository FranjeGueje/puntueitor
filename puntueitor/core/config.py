import json
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class Config:
    steam_api_key: str = ""
    steam_user_id: int = 0
    igdb_client_id: str = ""
    igdb_client_secret: str = ""

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
        else:
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.config = Config(**{k: v for k, v in data.items() if hasattr(Config, k)})
            except (json.JSONDecodeError, OSError):
                self.config = Config()

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(asdict(self.config), f, indent=4)

    @property
    def get(self) -> Config:
        return self.config
