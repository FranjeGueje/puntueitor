import binascii

from typing import Optional

class SteamGame():
    """Representa un juego de Steam."""

    def __init__(
        self,
        AppName: str,
        Exe: str,
        appid: int = 0,
        StartDir: str = "./",
        icon: str = "",
        ShortcutPath: str = "",
        LaunchOptions: str = "",
        IsHidden: int = 0,
        AllowDesktopConfig: int = 1,
        AllowOverlay: int = 1,
        OpenVR: int = 0,
        Devkit: int = 0,
        DevkitGameID: str = "",
        DevkitOverrideAppID: int = 0,
        LastPlayTime: int = 0,
        FlatpakAppID: str = "",
        tags: dict | None = None,
    ) -> None:

        self.appid = appid or self.generate_app_id(Exe, AppName)
        self.AppName = AppName
        self.Exe = Exe
        self.StartDir = StartDir
        self.icon = icon
        self.ShortcutPath = ShortcutPath
        self.LaunchOptions = LaunchOptions
        self.IsHidden = IsHidden
        self.AllowDesktopConfig = AllowDesktopConfig
        self.AllowOverlay = AllowOverlay
        self.OpenVR = OpenVR
        self.Devkit = Devkit
        self.DevkitGameID = DevkitGameID
        self.DevkitOverrideAppID = DevkitOverrideAppID
        self.LastPlayTime = LastPlayTime
        self.FlatpakAppID = FlatpakAppID
        self.tags = tags or {}

    def __str__(self) -> str:
        return str(self.to_dict())

    def to_dict(self) -> dict:
        return {
            'appid': self.appid,
            'AppName': self.AppName,
            'Exe': self.Exe,
            'StartDir': self.StartDir,
            'icon': self.icon,
            'ShortcutPath': self.ShortcutPath,
            'LaunchOptions': self.LaunchOptions,
            'IsHidden': self.IsHidden,
            'AllowDesktopConfig': self.AllowDesktopConfig,
            'AllowOverlay': self.AllowOverlay,
            'OpenVR': self.OpenVR,
            'Devkit': self.Devkit,
            'DevkitGameID': self.DevkitGameID,
            'DevkitOverrideAppID': self.DevkitOverrideAppID,
            'LastPlayTime': self.LastPlayTime,
            'FlatpakAppID': self.FlatpakAppID,
            'tags': self.tags
        }

    def get_appid_human(self) -> int:
        return self.appid + 2**32
    
    @staticmethod
    def generate_app_id(exe: str, name: str) -> int:
        key = exe + name
        crc_value = binascii.crc32(key.encode())
        return (crc_value | 0x80000000) - 2**32
    
    @staticmethod
    def from_dict(data:dict) -> Optional['SteamGame']:
        try:
            return SteamGame(
                appid = data.get("appid", 0),
                AppName = data.get("AppName", ""),
                Exe = data.get("Exe", ""),
                StartDir = data.get("StartDir", "./"),
                icon = data.get("icon", ""),
                ShortcutPath = data.get("ShortcutPath", ""),
                LaunchOptions = data.get("LaunchOptions", ""),
                IsHidden = data.get("IsHidden", 0),
                AllowDesktopConfig = data.get("AllowDesktopConfig", 1),
                AllowOverlay = data.get("AllowOverlay", 1),
                OpenVR = data.get("OpenVR", 0),
                Devkit = data.get("Devkit", 0),
                DevkitGameID = data.get("DevkitGameID", ""),
                DevkitOverrideAppID = data.get("DevkitOverrideAppID", 0),
                LastPlayTime = data.get("LastPlayTime", 0),
                FlatpakAppID = data.get("FlatpakAppID", ""),
                tags = data.get("tags", {})
            )
        except Exception:
            return None