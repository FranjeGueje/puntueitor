from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Center, Middle
from textual.widgets import Label, ListView, ListItem, Static, Footer
from textual import on


class UnknownMenuScreen(ModalScreen[str]):
    """Pantalla con opciones para un juego desconocido."""

    BINDINGS = [
        ("escape", "cancel", "Volver"),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="filtering-dialog"):
                    yield Label("Acción para juego desconocido", id="filtering-title")
                    yield ListView(
                        ListItem(Static("Buscar por título (IGDB)")),
                        ListItem(Static("Volver a buscar por tienda (IGDB)")),
                        ListItem(Static("Volver")),
                        id="unknown-menu-list",
                    )
        yield Footer()

    @on(ListView.Selected, "#unknown-menu-list")
    def on_selected(self, event: ListView.Selected) -> None:
        choices = ["search_title", "search_store", "back"]
        self.dismiss(choices[event.list_view.index])

    def action_cancel(self) -> None:
        self.dismiss(None)
