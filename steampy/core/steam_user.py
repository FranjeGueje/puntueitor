from typing import Optional
from pathlib import Path
import vdf

from .steam_shortcuts import SteamShortcuts

USER_ID_BASE = 76561197960265728


class SteamUser():
    """Representa un usuario de Steam."""

    def __init__(
        self,
        steam_id: int,
        account_name: str,
        personal_name: str,
        steam_path: Path
    ) -> None:
        self.steam_id = steam_id
        self.account_name = account_name
        self.personal_name = personal_name
        self.img_path = steam_path / "config/avatarcache/" / Path(str(steam_id) + ".png")
        self.userdata_path = steam_path / "userdata/" / Path(str(steam_id - USER_ID_BASE))
        self.grid_path = self.userdata_path / 'config/grid/'
        self.shortcuts = SteamShortcuts(self.path_vdf_shortcuts())

    def __str__(self) -> str:
        return (
            f"\033[1;35mID STEAM:\033[0m\t\t{self.steam_id}\n"
            f"\033[1;35mCUENTA:\033[0m\t\t\t{self.account_name}\n"
            f"\033[1;35mNOMBRE:\033[0m\t\t\t{self.personal_name}\n"
            f"\033[1;35mIMAGEN:\033[0m\t\t\t{self.img_path}\n"
            f"\033[1;35mRUTA:\033[0m\t\t\t{self.userdata_path}\n"
            f"\033[1;35mRUTA SHORTCUTS.VDF:\033[0m\t{self.path_vdf_shortcuts()}\n"
            f"\033[1;35mRUTA LOCALCONFIG.VDF:\033[0m\t{self.path_vdf_localconfig()}"
        )

    def path_vdf_shortcuts(self) -> Path:
        return self.userdata_path / "config/shortcuts.vdf"

    def path_vdf_localconfig(self) -> Path:
        return self.userdata_path / "config/localconfig.vdf"
    
    def get_library(self) -> dict:
        return self.shortcuts.data.get("shortcuts", {}) if self.shortcuts.data else {}

    @staticmethod
    def load_users(steam_path: Path | None = None) -> tuple['SteamUser']:
        steam_path = steam_path or Path.home() / ".local/share/Steam"
        login_users_path = steam_path / "config/loginusers.vdf"
        users_list = []
        
        try:
            with login_users_path.open() as f:
                data = vdf.load(f)

            for steam_id_str, user_data in data.get("users", {}).items():
                users_list.append(
                    SteamUser(
                        steam_id=int(steam_id_str),
                        account_name=user_data.get("AccountName", ""),
                        personal_name=user_data.get("PersonaName", ""),
                        steam_path=steam_path
                    )
                )
            return tuple(users_list)
        except Exception:
            return tuple()

    @staticmethod
    def load_user(steam_id: int, steam_path: Path | None = None) -> Optional['SteamUser']:
        steam_path = steam_path or Path.home() / ".local/share/Steam"
        login_users_path = steam_path / "/config/loginusers.vdf"
        try:
            with login_users_path.open() as f:
                data = vdf.load(f)
            for steam_id_str, user_data in data.get("users", {}).items():
                if int(steam_id_str) == steam_id:
                    return SteamUser(
                        steam_id=int(steam_id_str),
                        account_name=user_data.get("AccountName", ""),
                        personal_name=user_data.get("PersonaName", ""),
                        steam_path=steam_path
                    )
        except Exception:
            return None

    @staticmethod
    def get_all_games_from_users(steam_path: Path | None = None) -> set[int]:
        steam_path = steam_path or Path.home() / ".local/share/Steam"
        game_ids = set()
        for user in SteamUser.load_users(steam_path):
            shortcuts = user.get_library()
            for shortcut in shortcuts.values():
                game_ids.add(shortcut.get("appid", 0) + 2**32)

        return game_ids
