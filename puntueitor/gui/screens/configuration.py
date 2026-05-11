from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal, Center, Middle
from textual.widgets import Input, Label, Button, Header, Footer, Checkbox
from textual.widgets import Input, Label, Button, Header, Footer, Checkbox

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

                    yield Label("Tiendas a cargar", classes="section-title")
                    yield Checkbox("Steam", id="store-steam", value=True)
                    yield Checkbox("GOG / Epic / Amazon (via Heroic)", id="store-heroic")

                    yield Label("Carpeta de Heroic (opcional)", classes="section-title")
                    yield Label("Deja vacío para auto-detectar")
                    yield Input(id="heroic-path", placeholder="~/.config/heroic")

                    with Horizontal(id="config-buttons"):
                        yield Button("Guardar", variant="success", id="btn-save")
                        yield Button("Cancelar", variant="error", id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Configuración"
        config = ConfigManager().get


        self.query_one("#igdb-client-id", Input).value = config.igdb_client_id or ""
        self.query_one("#igdb-client-secret", Input).value = config.igdb_client_secret or ""
        self.query_one("#steam-api-key", Input).value = config.steam_api_key or ""
        self.query_one("#steam-user-id", Input).value = str(config.steam_user_id) if config.steam_user_id else ""

        self.query_one("#store-steam", Checkbox).value = config.steam_is_active
        self.query_one("#store-heroic", Checkbox).value = config.heroic_is_active

        self.query_one("#heroic-path", Input).value = config.heroic_path or ""

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

        config.steam_is_active = self.query_one("#store-steam", Checkbox).value
        config.heroic_is_active = self.query_one("#store-heroic", Checkbox).value

        config.heroic_path = self.query_one("#heroic-path", Input).value

        manager.save()
        self.app.notify("Configuración guardada correctamente.", severity="information")
        self.dismiss()

    def action_cancel(self) -> None:
        self.dismiss()