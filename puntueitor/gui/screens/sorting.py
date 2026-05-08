from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Center, Middle
from textual.widgets import Label, Static, Footer

class SortingScreen(ModalScreen[tuple[str, bool]]):
    """Pantalla modal para seleccionar el método de ordenación."""
    
    BINDINGS = [
        ("a", "select('title', False)", "a/A Nombre Alfabético"),
        ("A", "select('title', True)", ""),
        ("u", "select('user_score', True)", "u/U Puntuación usuario"),
        ("U", "select('user_score', False)", ""),
        ("c", "select('critic_score', True)", "c/C Puntuación crítica"),
        ("C", "select('critic_score', False)", ""),
        ("m", "select('mixed', True)", "m/M Puntuación media"),
        ("M", "select('mixed', False)", ""),
        ("d", "select('duration', False)", "d/D Duración"),
        ("D", "select('duration', True)", ""),
        ("escape", "cancel", "ESC Volver"),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="sorting-dialog"):
                    yield Label("Ordenar biblioteca por...", id="sorting-title")
                    yield Static("Nombre Alfabético", classes="sort-option")
                    yield Static("Puntuación de usuarios", classes="sort-option")
                    yield Static("Puntuación de crítica", classes="sort-option")
                    yield Static("Puntuación media", classes="sort-option")
                    yield Static("Duración", classes="sort-option")
                    yield Label("Pulse una tecla para ordenar por un criterio", id="sorting-hint")
        yield Footer()

    def action_select(self, criteria: str, reverse: bool = False) -> None:
        self.dismiss((criteria, reverse))

    def action_cancel(self) -> None:
        self.dismiss(None)
