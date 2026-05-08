from pathlib import Path
import urllib.parse
import subprocess

from .steam_library import SteamLibrary
from .steam_config import SteamConfig
from .steam_user import SteamUser

class Steam():
    """Representa una instalación de Steam."""
    def __init__(self, steam_path: Path | None = None) -> None:
        self.steam_path = steam_path or Path.home() / ".local/share/Steam"
        self.config = SteamConfig(self.steam_path)
        self.library = SteamLibrary(self.steam_path)
        self.users = SteamUser.load_users(self.steam_path)

    def reload_config(self) -> None:
        self.config = SteamConfig(self.steam_path)
    
    def reload_library(self) -> None:
        self.library = SteamLibrary(self.steam_path)
    
    def reload_users(self) -> None:
        self.users = SteamUser.load_users(self.steam_path)
    
    def get_all_shortcuts(self) -> set[int]:
        all_shortcuts: set[int] = set()
        for user in self.users:
            all_shortcuts.update(user.get_all_games_from_users())
        return all_shortcuts
    
    @staticmethod
    def add_steam_game(game_name: str) -> subprocess.CompletedProcess:
        # mimeapps_list_path = Path.home() / ".config/mimeapps.list"

        # # Check if "x-scheme-handler/steam=" exists in mimeapps.list
        # with open(mimeapps_list_path, "r") as file:
        #     mimeapps_content = file.read()

        # if "x-scheme-handler/steam=" not in mimeapps_content.lower():
        #     with open(mimeapps_list_path, "a") as file:
        #         file.write("x-scheme-handler/steam=steam.desktop;\n")

        # Construct the steam URL with the encoded game name
        encoded_url = "steam://addnonsteamgame/{}".format(
            urllib.parse.quote(game_name, safe=''))

        # Create a temporary file
        with open('/tmp/addnonsteamgamefile', 'w'):
            pass

        # Open the URL using xdg-open
        return subprocess.run("xdg-open " + encoded_url, shell=True)