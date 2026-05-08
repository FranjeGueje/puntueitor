from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal, Center, Middle
from textual.widgets import Input, Label, Button, Header, Footer

from puntueitor.core.config import ConfigManager

class ConfigurationScreen(Screen):
    BINDINGS = [("escape", "cancel", "Cancelar")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle():
            with Center():
                with Vertical(id="config-dialog"):
                    yield Label("Configuración IGDB", classes="section-title")
                    yield Label("Client ID")
                    yield Input(id="igdb-client-id")
                    yield Label("Client Secret")
                    yield Input(password=True, id="igdb-client-secret")
                    
                    yield Label("Configuración Steam", classes="section-title")
                    yield Label("Steam User ID (Numérico)")
                    yield Input(id="steam-user-id", type="number")
                    yield Label("API Key")
                    yield Input(password=True, id="steam-api-key")

                    yield Label("Próximas Integraciones", classes="section-title")
                    yield Input(placeholder="GOG - Próximamente", disabled=True)
                    yield Input(placeholder="Epic Games - Próximamente", disabled=True)

                    with Horizontal(id="config-buttons"):
                        yield Button("Guardar", variant="success", id="btn-save")
                        yield Button("Cancelar", variant="error", id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Configuración"
        config = ConfigManager().get
        
        # Populate current values
        self.query_one("#igdb-client-id", Input).value = config.igdb_client_id or ""
        self.query_one("#igdb-client-secret", Input).value = config.igdb_client_secret or ""
        self.query_one("#steam-api-key", Input).value = config.steam_api_key or ""
        self.query_one("#steam-user-id", Input).value = str(config.steam_user_id) if config.steam_user_id else ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self.action_save()
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_save(self) -> None:
        manager = ConfigManager()
        config = manager.get
        
        config.igdb_client_id = self.query_one("#igdb-client-id", Input).value
        config.igdb_client_secret = self.query_one("#igdb-client-secret", Input).value
        config.steam_api_key = self.query_one("#steam-api-key", Input).value
        
        user_id_str = self.query_one("#steam-user-id", Input).value
        try:
            config.steam_user_id = int(user_id_str) if user_id_str else 0
        except ValueError:
            config.steam_user_id = 0
            
        manager.save()
        self.app.notify("Configuración guardada correctamente.", severity="information")
        self.dismiss()

    def action_cancel(self) -> None:
        self.dismiss()
