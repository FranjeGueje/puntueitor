from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Center, Middle
from textual.widgets import Label, Input, Footer

class FilterInputScreen(ModalScreen[str]):
    """Pantalla modal con un campo de entrada para el filtro."""
    
    def __init__(self, title: str, placeholder: str = "", **kwargs):
        self.dialog_title = title
        self.placeholder = placeholder
        super().__init__(**kwargs)

    BINDINGS = [
        ("escape", "cancel", "ESC Cancelar"),
        ("enter", "submit", "ENTER Aceptar"),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="input-dialog"):
                    yield Label(self.dialog_title, id="input-title")
                    yield Input(placeholder=self.placeholder, id="filter-input")
                    yield Label("ENTER para aplicar | ESC para cancelar", id="input-hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def action_submit(self) -> None:
        value = self.query_one(Input).value
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)
