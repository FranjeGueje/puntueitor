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
        """
        Auto-detecta o usa el path personalizado de Heroic.

        Que la ruta configurada no exista se AVISA. Antes se caía a la
        autodetección en silencio: el usuario veía la ruta que él había puesto
        en Configuración y unos juegos que salían (o no) de otro sitio, sin
        nada en el log que lo explicara.
        """
        if custom_path:
            path = Path(custom_path)
            if path.is_dir():
                # A DEBUG: la ruta ya sale una vez en la cabecera de la sesión
                # (`logging_setup`), y esto se llama una vez por tienda.
                logger.debug(f"Heroic: usando la carpeta configurada {path}")
                return path
            logger.warning(
                f"la carpeta de Heroic configurada no existe: {path}. "
                "Se buscará en las rutas habituales (Opciones → Configuración)"
            )

        for path in self.DEFAULT_PATHS:
            if path.is_dir():
                logger.debug(f"Heroic: encontrado en {path}")
                return path

        logger.warning(
            "no se encuentra la carpeta de Heroic. Se ha buscado en: "
            + ", ".join(str(p) for p in self.DEFAULT_PATHS)
        )
        return None

    def _load_library_file(self, library_file: Path) -> list[dict[str, Any]]:
        """Carga un archivo JSON de biblioteca."""
        if not library_file.exists():
            # No es un error: quien no tenga cuenta de Amazon no tiene ese
            # fichero. Pero se dice, porque "Epic activo y cero juegos" casi
            # siempre es esto — Heroic no ha llegado a escribir su caché.
            logger.info(
                f"Heroic no tiene todavía {library_file.name}: ábrelo e inicia "
                "sesión en esa tienda para que genere su biblioteca"
            )
            return []

        try:
            with open(library_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(
                f"el fichero de Heroic {library_file} está corrupto y no se "
                f"puede leer: {e}"
            )
            return []
        except OSError as e:
            logger.error(f"no se puede leer {library_file}: {e}")
            return []

        games = data.get("games") or data.get("library") or []
        if not games:
            logger.warning(
                f"{library_file.name} no tiene ningún juego dentro: puede que "
                "la sesión de esa tienda haya caducado en Heroic"
            )
        else:
            logger.info(f"Heroic: {len(games)} juegos en {library_file.name}")
        return games

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