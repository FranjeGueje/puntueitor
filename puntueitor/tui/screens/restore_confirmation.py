from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Center, Middle
from textual.widgets import Label, Button
from textual.screen import ModalScreen


class RestoreConfirmationScreen(ModalScreen[bool]):
    """
    Confirmación de restaurar una copia, que sobrescribe TODO.

    Hermana de `ReloadConfirmationScreen` y con sus mismos estilos: las dos
    son la última pregunta antes de perder datos, y conviene que se vean
    igual para que se lean igual de despacio.
    """

    def __init__(self, path: str, **kwargs):
        self.path = path
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="reload-dialog"):
                    yield Label("¡ADVERTENCIA!", id="reload-title-warn")
                    yield Label(
                        f"Se restaurará la copia:\n{self.path}\n\n"
                        "Se SOBRESCRIBIRÁN todos tus datos actuales: "
                        "biblioteca, estados y configuración.\n"
                        "Al terminar, Puntueitor se cerrará.",
                        id="reload-message"
                    )
                    with Horizontal(id="reload-buttons"):
                        yield Button("Cancelar", variant="default", id="cancel")
                        yield Button("RESTAURAR", variant="error", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")
