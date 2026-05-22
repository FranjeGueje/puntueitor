from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Center, Middle
from textual.widgets import Label, Button
from textual.screen import ModalScreen

class ReloadConfirmationScreen(ModalScreen[bool]):
    """Pantalla de confirmación para recarga total de la biblioteca."""

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="reload-dialog"):
                    yield Label("¡ADVERTENCIA!", id="reload-title-warn")
                    yield Label(
                        "Esta acción borrará TODA la caché local (SQLite).\n"
                        "Se volverán a descargar todos los juegos desde Steam e IGDB.\n"
                        "El proceso puede ser costoso y tardar varios minutos.",
                        id="reload-message"
                    )
                    with Horizontal(id="reload-buttons"):
                        yield Button("Cancelar", variant="default", id="cancel")
                        yield Button("BORRAR Y RECARGAR", variant="error", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)
