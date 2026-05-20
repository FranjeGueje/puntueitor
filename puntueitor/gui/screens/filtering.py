from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Center, Middle
from textual.widgets import Label, Static, Footer

class FilteringScreen(ModalScreen[str]):
    """Pantalla modal para seleccionar el tipo de filtro."""
    
    BINDINGS = [
        ("n", "select('name')", "n Nombre"),
        ("d", "select('duration')", "d Duración"),
        ("t", "select('finished:true')", "t Terminados"),
        ("T", "select('finished:false')", "T No terminados"),
        ("f", "select('favorite:true')", "f Favoritos"),
        ("F", "select('favorite:false')", "F No favoritos"),
        ("b", "select('backlog:true')", "b Backlog"),
        ("B", "select('backlog:false')", "B No backlog"),
        ("x", "select('clear')", "x Limpiar Filtros"),
        ("escape", "cancel", "ESC Volver"),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="filtering-dialog"):
                    yield Label("Filtrar biblioteca por...", id="filtering-title")
                    yield Static("Nombre", classes="filter-option")
                    yield Static("Duración", classes="filter-option")
                    yield Static("Terminados", classes="filter-option")
                    yield Static("No terminados", classes="filter-option")
                    yield Static("Favoritos", classes="filter-option")
                    yield Static("No favoritos", classes="filter-option")
                    yield Static("Backlog", classes="filter-option")
                    yield Static("No backlog", classes="filter-option")
                    yield Static("Limpiar Filtros", classes="filter-option")
                    yield Label("Pulse una tecla para filtrar", id="filtering-hint")
        yield Footer()

    def action_select(self, filter_type: str) -> None:
        self.dismiss(filter_type)

    def action_cancel(self) -> None:
        self.dismiss(None)
