from pathlib import Path

import vdf


class SteamConfig():
    """Representa la configuración de Steam."""

    def __init__(self, steam_path: Path | None = None) -> None:
        self.steam_path = Path(steam_path or Path.home() / ".local/share/Steam")
        self.file = self.steam_path / "config/config.vdf"
        self.data = SteamConfig.load_config(self.file)
        
    @staticmethod
    def load_config(file_path: Path) -> dict | None:
        try:
            with file_path.open() as f:
                return vdf.load(f)
        except Exception:
            return None
    
    @staticmethod
    def save_config_to_file(file_path: Path, data: dict) -> bool:
        try:
            with file_path.open("w") as f:
                vdf.dump(data, f, pretty=True)
            return True
        except Exception:
            return False
            
    def get_CompatToolMapping(self) -> dict:
        if self.data:
            return self.data['InstallConfigStore']['Software']['Valve']['Steam']['CompatToolMapping']
        else:
            return {}

    def set_compat_tool_mapping(self, ctm: dict) -> bool:
        if not self.data:
            return False
        try:
            self.data['InstallConfigStore']['Software']['Valve']['Steam']['CompatToolMapping'] = ctm
            return self.save_config_to_file(self.file, self.data)
        except Exception:
            return False
    
    def save_SteamConfig(self) -> bool:
        return self.save_config_to_file(self.file, self.data) if self.data else False
