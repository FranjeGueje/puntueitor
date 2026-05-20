from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Center, Middle
from textual.widgets import Label, DataTable, Footer
from textual import on


class IGDBSearchResults(ModalScreen[dict | None]):
    """Muestra los resultados de una búsqueda en IGDB."""

    def __init__(self, results: list[dict], **kwargs):
        self.results = results
        super().__init__(**kwargs)

    BINDINGS = [
        ("escape", "cancel", "Volver"),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="igdb-results-dialog"):
                    yield Label("Resultados de búsqueda", id="igdb-results-title")
                    yield DataTable(id="igdb-results-table", cursor_type="row")
                    yield Label("ENTER para seleccionar | ESC para volver", id="igdb-results-hint")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#igdb-results-table", DataTable)
        table.add_column("Título", width=60)
        table.add_column("Año", width=6)
        table.add_column("ID IGDB", width=10)

        for r in self.results:
            year = ""
            ts = r.get("first_release_date")
            if ts:
                try:
                    year = str(datetime.fromtimestamp(ts, tz=timezone.utc).year)
                except (OSError, ValueError, OverflowError):
                    pass
            table.add_row(
                r.get("name", "—"),
                year,
                str(r.get("id", "")),
                key=str(r["id"]),
            )

    @on(DataTable.RowSelected, "#igdb-results-table")
    def on_selected(self, event: DataTable.RowSelected) -> None:
        igdb_id = event.row_key.value
        for r in self.results:
            if str(r["id"]) == igdb_id:
                self.dismiss(r)
                return

    def action_cancel(self) -> None:
        self.dismiss(None)
