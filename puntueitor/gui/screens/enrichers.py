from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Center, Middle
from textual.widgets import Label, Static, Footer

class EnrichersScreen(ModalScreen[str]):
    """Pantalla modal para seleccionar el enriquecedor."""
    
    BINDINGS = [
        ("h", "select('hltb')", "h HowLongToBeat"),
        ("escape", "cancel", "ESC Volver"),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="enrichers-dialog"):
                    yield Label("Enriquecer biblioteca con...", id="enrichers-title")
                    yield Static("HowLongToBeat", classes="enricher-option")
                    yield Label("Pulse una tecla para empezar", id="enrichers-hint")
        yield Footer()

    def action_select(self, enricher_type: str) -> None:
        self.dismiss(enricher_type)

    def action_cancel(self) -> None:
        self.dismiss(None)
