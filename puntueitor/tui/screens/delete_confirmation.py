from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal, Center, Middle
from textual.widgets import Label, Button


class DeleteConfirmationScreen(ModalScreen[bool]):

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="delete-confirm-dialog"):
                    yield Label("¿Desconocer este juego?", id="delete-confirm-title")
                    yield Label(
                        "El juego desaparecerá de esta lista\n"
                        "y se añadirá a la lista de desconocidos.\n"
                        "Podrás volver a identificarlo más tarde.",
                        id="delete-confirm-message",
                    )
                    with Horizontal(id="delete-confirm-buttons"):
                        yield Button("Cancelar", variant="default", id="cancel")
                        yield Button("Desconocer", variant="error", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)
