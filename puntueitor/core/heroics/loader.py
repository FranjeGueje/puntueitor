import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class HeroicsLoader:
    """Carga bibliotecas desde Heroic Games Launcher."""

    DEFAULT_PATHS = [
        Path.home() / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config" / "heroic",
        Path.home() / ".config" / "heroic",
    ]

    def find_heroic_path(self, custom_path: str | None = None) -> Path | None:
        """Auto-detecta o usa path personalizado de Heroic."""
        if custom_path:
            path = Path(custom_path)
            if path.exists():
                logger.info(f"Using custom Heroic path: {path}")
                return path

        for path in self.DEFAULT_PATHS:
            if path.exists():
                logger.info(f"Auto-detected Heroic path: {path}")
                return path

        logger.warning("No Heroic config path found")
        return None

    def _load_library_file(self, library_file: Path) -> list[dict[str, Any]]:
        """Carga un archivo JSON de biblioteca."""
        if not library_file.exists():
            logger.debug(f"Library file not found: {library_file}")
            return []

        try:
            with open(library_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                games = data.get("games") or data.get("library") or []
                logger.info(f"Loaded {len(games)} games from {library_file.name}")
                return games
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {library_file}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error reading {library_file}: {e}")
            return []

    def get_gog_games(self, heroic_path: Path) -> list[dict[str, Any]]:
        """Carga juegos de GOG desde store_cache/gog_library.json."""
        library_file = heroic_path / "store_cache" / "gog_library.json"
        return self._load_library_file(library_file)

    def get_epic_games(self, heroic_path: Path) -> list[dict[str, Any]]:
        """Carga juegos de Epic desde store_cache/legendary_library.json."""
        library_file = heroic_path / "store_cache" / "legendary_library.json"
        return self._load_library_file(library_file)

    def get_amazon_games(self, heroic_path: Path) -> list[dict[str, Any]]:
        """Carga juegos de Amazon desde store_cache/nile_library.json."""
        library_file = heroic_path / "store_cache" / "nile_library.json"
        return self._load_library_file(library_file)

    def get_all_heroic_games(self, heroic_path: Path) -> dict[str, list[dict[str, Any]]]:
        """Carga todas las bibliotecas de Heroic (GOG, Epic, Amazon)."""
        return {
            "gog": self.get_gog_games(heroic_path),
            "epic": self.get_epic_games(heroic_path),
            "amazon": self.get_amazon_games(heroic_path),
        }