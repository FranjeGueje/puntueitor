import vdf
from pathlib import Path


class CompatTool():
    """Representa una herramienta de compatibilidad de Steam."""

    def __init__(self, internal_name: str, display_name: str, path: str) -> None:
        self.internal_name = internal_name
        self.display_name = display_name
        self.path = path

    @staticmethod
    def load_compat_tools(steam_path: Path | None = None) -> tuple['CompatTool']:
        steam_path = steam_path or Path.home() / ".local/share/Steam"
        compat_dir = steam_path / "compatibilitytools.d"
        compat_list = list()
        
        if compat_dir.is_dir():
            for folder in compat_dir.iterdir():
                if folder.is_dir():
                    vdf_path = folder / "compatibilitytool.vdf"
                    if vdf_path.is_file():
                        try:
                            with vdf_path.open() as f:
                                data = vdf.load(f)
                            tools = data.get("compatibilitytools", {}).get("compat_tools", {})
                            for internal_name, tool_data in tools.items():
                                display_name = tool_data.get("display_name", internal_name)
                                compat_list.append(
                                    CompatTool(internal_name, display_name, str(folder))
                                )

                        except Exception:
                            continue  # Silenciar errores de lectura/parsing
            
            # Añadir herramientas por defecto
            compat_list.extend([
                CompatTool("proton_8", "Proton 8", str(steam_path / "steamapps/common/Proton 8.0")),
                CompatTool("proton_experimental", "Proton Experimental", str(steam_path / "steamapps/common/Proton - Experimental"))
            ])
        
        return(tuple(compat_list))



class CompatToolManager():
    """Gestiona el mapeo entre AppIDs y herramientas de compatibilidad."""
    def __init__(self, compat_tool_mapping:dict, compat_tools: tuple['CompatTool']) -> None:
        self.compat_tool_mapping = compat_tool_mapping
        self.compat_tools = compat_tools

    def get(self, appid_human:int) -> str:
        result = self.compat_tool_mapping[str(appid_human)] if str(appid_human) in self.compat_tool_mapping.keys() else None
        return result['name'] if result else ''

    def get_compat_tool(self, name: str) -> CompatTool | None:
        for ct in self.compat_tools:
            if ct.internal_name == name or ct.display_name == name:
                return ct
        return None
    
    def assign_compat_tool(self, appid_human:int, compat_tool: CompatTool) -> None:
        self.compat_tool_mapping[str(appid_human)] = {
            'name': compat_tool.internal_name if compat_tool else '',
            'config': '',
            'priority': '250' if compat_tool else '0'
        }
        