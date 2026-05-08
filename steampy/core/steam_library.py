from pathlib import Path
import vdf

class SteamLibrary():
    """Representa la biblioteca de Steam."""

    def __init__(self, steam_path: Path | None = None) -> None:
        self.steam_path = Path(steam_path or Path.home() / ".local/share/Steam")
        self.file = self.steam_path / "steamapps/libraryfolders.vdf"
        self.data = SteamLibrary.load_library(self.file)
        
    @staticmethod
    def load_library(file_path: Path) -> dict | None:
        try:
            with file_path.open() as f:
                return vdf.load(f)
        except Exception:
            return None
    
    def get_all_Steam_games(self) -> set[int]:
        ids_games = set()
        if self.data:
            for k,v in self.data['libraryfolders'].items():
                for h,i in v['apps'].items():
                    ids_games.add(int(h))
            return ids_games
        return ids_games
    