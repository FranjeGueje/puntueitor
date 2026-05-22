from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal, Center, Middle
from textual.widgets import Label, Button

class QuitConfirmation(ModalScreen[bool]):
    """Pantalla modal para confirmar la salida de la aplicación."""

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="quit-dialog"):
                    yield Label("¿Deseas salir de Puntueitor?", id="quit-message")
                    with Horizontal(id="quit-buttons"):
                        yield Button("Sí", id="yes")
                        yield Button("No", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.dismiss(True)
        else:
            self.dismiss(False)
