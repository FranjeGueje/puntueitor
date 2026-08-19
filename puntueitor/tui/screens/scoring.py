from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal, Container
from textual.widgets import Label, Static, Footer, ListItem, ListView
from textual import on

from puntueitor.core.scoring import catalog
from puntueitor.tui.screens.scoring_config import ScoringConfigScreen

#: Los sistemas salen de `core/scoring/catalog.py`, que es donde viven sus
#: textos. Antes estaban escritos aquí Y en `gui3d/scoring_info.py`, y las dos
#: copias acabaron divergiendo: esta tenía frases y una recomendación final
#: que el carrusel no enseñaba.
#:
#: La terminal tiene sitio de sobra, así que aquí se enseña todo: la
#: descripción y la recomendación.
def _info(sistema) -> dict[str, str]:
    return {
        "title": sistema.title,
        "desc": f"{sistema.description}\n\n{sistema.recommendation}",
    }


SCORING_INFO = {
    sistema.key: _info(sistema) for sistema in catalog.SYSTEMS
}


class ScoringScreen(ModalScreen[str]):
    """Pantalla modal mejorada para seleccionar el sistema de scoring."""
    
    BINDINGS = [
        ("enter", "select", "Seleccionar"),
        ("c", "configure", "Configurar"),
        ("escape", "cancel", "Volver"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="scoring-dialog-expanded"):
            yield Label("Puntueitor - Sistemas de Scoring", id="scoring-title")
            
            with Horizontal(id="scoring-content"):
                with ListView(id="scoring-list"):
                    yield ListItem(Label("Mixed Score"), id="mixed")
                    yield ListItem(Label("Weighted Score"), id="weighted")
                    yield ListItem(Label("Available Time"), id="time")
                    yield ListItem(Label("Genre Match"), id="genre")
                
                with Container(id="scoring-info-panel"):
                    yield Label("Detalles del sistema", id="info-title")
                    yield Static("", id="info-body")
                    
            yield Label("↑↓ Navegar | ENTER Seleccionar | c Config", id="scoring-hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#scoring-list").focus()

    @on(ListView.Highlighted)
    def update_preview(self, event: ListView.Highlighted) -> None:
        """Actualiza la previsualización automáticamente al navegar."""
        if event.item:
            sid = event.item.id
            info = SCORING_INFO.get(sid)
            if info:
                self.query_one("#info-title").update(info["title"])
                self.query_one("#info-body").update(info["desc"])

    @on(ListView.Selected)
    def handle_selection(self, event: ListView.Selected) -> None:
        """Maneja la selección al pulsar ENTER sobre un elemento."""
        if event.item:
            self.dismiss(event.item.id)

    def action_select(self) -> None:
        """Maneja la acción de selección (fallback para el binding)."""
        selected_item = self.query_one("#scoring-list").highlighted_child
        if selected_item:
            self.dismiss(selected_item.id)

    def action_configure(self) -> None:
        list_view = self.query_one("#scoring-list", ListView)
        selected = list_view.index
        scoring_type = ["mixed", "weighted", "time", "genre"][selected]
        self.app.push_screen(ScoringConfigScreen(scoring_type))

    def action_cancel(self) -> None:
        self.dismiss(None)
