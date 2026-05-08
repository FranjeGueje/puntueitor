from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Center, Middle
from textual.widgets import Label, Static

class SortingScreen(ModalScreen[str]):
    """Pantalla modal para seleccionar el método de ordenación."""
    
    BINDINGS = [
        ("a", "select('title')", "Título"),
        ("u", "select('user_score')", "User Score"),
        ("c", "select('critic_score')", "Critic Score"),
        ("d", "select('duration')", "Duración"),
        ("m", "select('mixed')", "Mixto"),
        ("escape", "cancel", "Cancelar"),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="sorting-dialog"):
                    yield Label("Ordenar biblioteca por...", id="sorting-title")
                    yield Static("[A] Título (Alfabético)", classes="sort-option")
                    yield Static("[U] Puntuación de Usuarios", classes="sort-option")
                    yield Static("[C] Puntuación de Crítica", classes="sort-option")
                    yield Static("[D] Duración (Más cortos)", classes="sort-option")
                    yield Static("[M] Mixto (Recomendado)", classes="sort-option")
                    yield Label("Pulsa una tecla o ESC para volver", id="sorting-hint")

    def action_select(self, criteria: str) -> None:
        self.dismiss(criteria)

    def action_cancel(self) -> None:
        self.dismiss(None)
