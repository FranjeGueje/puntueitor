from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Center, Middle
from textual.widgets import Label, Static, Footer

class FilteringScreen(ModalScreen[str]):
    """Pantalla modal para seleccionar el tipo de filtro."""

    BINDINGS = [
        ("n", "select('name')", "n Nombre"),
        ("d", "select('duration')", "d Duración"),
        ("f", "select('finished')", "f Terminado"),
        ("F", "select('not_finished')", "F No terminado"),
        ("b", "select('backlog')", "b Backlog"),
        ("B", "select('not_backlog')", "B No backlog"),
        ("v", "select('favorite')", "v Favorito"),
        ("V", "select('not_favorite')", "V No favorito"),
        ("h", "select('hidden')", "h Oculto"),
        ("H", "select('not_hidden')", "H No oculto"),
        ("x", "select('clear')", "x Limpiar Filtros"),
        ("escape", "cancel", "ESC Volver"),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="filtering-dialog"):
                    yield Label("Filtrar biblioteca por...", id="filtering-title")
                    yield Static("Nombre (n)        Duración (d)", classes="filter-option")
                    yield Static("Terminado (f)     No terminado (F)", classes="filter-option")
                    yield Static("Backlog (b)       No backlog (B)", classes="filter-option")
                    yield Static("Favorito (v)      No favorito (V)", classes="filter-option")
                    yield Static("Oculto (h)        No oculto (H)", classes="filter-option")
                    yield Static("Limpiar Filtros (x)", classes="filter-option")
                    yield Label("Pulse una tecla para filtrar", id="filtering-hint")
        yield Footer()

    def action_select(self, filter_type: str) -> None:
        self.dismiss(filter_type)

    def action_cancel(self) -> None:
        self.dismiss(None)
