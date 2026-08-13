from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal, Center, Middle
from textual.widgets import Label, Checkbox, Button

from puntueitor.core.models import Game
from puntueitor.tui.screens.delete_confirmation import DeleteConfirmationScreen


class GameOptionsScreen(ModalScreen[dict | None]):

    BINDINGS = [
        ("escape", "close_screen", "Salir"),
    ]

    def __init__(self, game: Game):
        super().__init__()
        self.game = game

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="game-options-dialog"):
                    yield Label(f"Opciones de: {self.game.title}", id="game-options-title")
                    yield Checkbox("Terminado", value=self.game.finished, id="cb-finished")
                    yield Checkbox("Oculto", value=self.game.hidden, id="cb-hidden")
                    yield Checkbox("Pendiente (Backlog)", value=self.game.backlog, id="cb-backlog")
                    yield Checkbox("Favorito", value=self.game.favorite, id="cb-favorite")
                    with Horizontal(id="game-options-buttons"):
                        yield Button("Guardar", variant="primary", id="save")
                        yield Button("Enriquecer", variant="success", id="enrich")
                        yield Button("Cancelar", variant="default", id="cancel")
                        yield Button("Desconocer", variant="error", id="delete")

    def action_close_screen(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.dismiss({
                "finished": self.query_one("#cb-finished", Checkbox).value,
                "hidden": self.query_one("#cb-hidden", Checkbox).value,
                "backlog": self.query_one("#cb-backlog", Checkbox).value,
                "favorite": self.query_one("#cb-favorite", Checkbox).value,
            })
        elif event.button.id == "enrich":
            self.dismiss({"__enrich__": True})
        elif event.button.id == "delete":
            def on_delete_confirm(confirmed: bool) -> None:
                if confirmed:
                    self.dismiss({"__delete__": True})
            self.app.push_screen(DeleteConfirmationScreen(), on_delete_confirm)
        else:
            self.dismiss(None)
