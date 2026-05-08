from pathlib import Path
from typing import Optional

import vdf
from .steam_game import SteamGame


class SteamShortcuts():
    """Representa el archivo de accesos directos de Steam."""

    def __init__(self, path_vdf: Path) -> None:
        self.file = path_vdf
        self.data = self.load_shortcuts(path_vdf)
        
    
    @staticmethod
    def load_shortcuts(file_path: Path) -> dict | None:
        try:
            with file_path.open("rb") as file:
                return vdf.binary_load(file)
        except (FileNotFoundError, Exception):
            return None
    
    @staticmethod
    def save_games(file_path: Path, games: tuple[SteamGame]) -> bool:
        data = {'shortcuts':{}}
        for i, game in enumerate(games):
            if game:
                data["shortcuts"][str(i)] = game.to_dict()
        try:
            with file_path.open("wb") as file:
                file.write(vdf.binary_dumps(data))
            return True
        except Exception:
            return False
    
    def get_game(self, id:int) -> Optional['SteamGame']:
        for game in self.get_games():
            if game and id == game.get_appid_human():
                return game
        return None
        
    def get_games(self) -> tuple[SteamGame]:
        games = []
        if self.data:
            for k, v in self.data['shortcuts'].items():
                games.append(SteamGame.from_dict(v))
        return tuple(games)
    
    def save_shortcuts(self, file_path: Path) -> bool:
        if not self.data:
            return False
        try:
            with file_path.open("wb") as file:
                file.write(vdf.binary_dumps(self.data))
            return True                
        except Exception:
            return False
    
    def add_game(self, game: SteamGame)-> bool:
        if not self.data:
            return False
        try:
            index = str(len(self.data["shortcuts"]))
            self.data["shortcuts"][index] = game.to_dict()
            return True
        except Exception:
            return False
    
    def modify_game(self, game: SteamGame)-> bool:
        if not self.data:
            return False
        try:
            game_list = self.data['shortcuts']
            for key, game_data in game_list.items():
                if game_data.get('appid') == game.appid:
                    game_data['AppName'] = game.AppName
                    game_data['Exe'] = game.Exe
                    game_data['StartDir'] = game.StartDir
                    game_data['icon'] = game.icon
                    game_data['ShortcutPath'] = game.ShortcutPath
                    game_data['LaunchOptions'] = game.LaunchOptions
                    game_data['IsHidden'] = game.IsHidden
                    game_data['AllowDesktopConfig'] = game.AllowDesktopConfig
                    game_data['AllowOverlay'] = game.AllowOverlay
                    game_data['OpenVR'] = game.OpenVR
                    game_data['Devkit'] = game.Devkit
                    game_data['DevkitGameID'] = game.DevkitGameID
                    game_data['DevkitOverrideAppID'] = game.DevkitOverrideAppID
                    game_data['LastPlayTime'] = game.LastPlayTime
                    game_data['FlatpakAppID'] = game.FlatpakAppID
                    game_data['tags'] = game.tags
                    return True
            return False
        except Exception:
            return False
        
    def remove_game(self, appid: int)-> bool:
        if not self.data:
            return False
        try:
            pos = len(self.data['shortcuts'])
            for i in range(pos):
                if self.data['shortcuts'][str(i)]['appid'] == appid :
                    for j in range(i,pos -1):
                        self.data['shortcuts'][str(j)] = self.data['shortcuts'][str(j+1)]
                    del(self.data['shortcuts'][str(pos-1)])
                    return True
            return False
        except Exception:
            return False


    def rename_game(self, original_name: str, new_name: str) -> bool:
        if not self.data:
            return False
        try:
            game_list = self.data['shortcuts']
            for key, game_data in game_list.items():
                if game_data.get('AppName') == original_name:
                    game_data['AppName'] = new_name
                    return True
            return False
        except Exception:
            return False
    