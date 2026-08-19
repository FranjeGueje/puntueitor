from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Container, ScrollableContainer, Horizontal
from textual.widgets import Label, Input, Button, Checkbox, Footer
from textual import on

from puntueitor.core import paths
from puntueitor.core.config import load_scoring, save_scoring, DEFAULT_MIXED_WEIGHTS, DEFAULT_WEIGHTED_WEIGHTS, DEFAULT_AVAILABLE_HOURS


class ScoringConfigScreen(ModalScreen[dict]):
    """Pantalla para configurar el sistema de scoring seleccionado."""

    BINDINGS = [
        ("escape", "cancel", "Cancelar"),
    ]

    TITLES = {
        "mixed": "Mixed Score: Ponderaciones",
        "weighted": "Weighted Score: Ponderaciones",
        "time": "Available Time: Horas disponibles",
        "genre": "Genre Match: Géneros preferidos",
    }

    def __init__(self, scoring_type: str = "mixed", **kwargs):
        super().__init__(**kwargs)
        self.scoring_type = scoring_type
        self._input_refs = {}

    def compose(self) -> ComposeResult:
        title = self.TITLES.get(self.scoring_type, "Configurar Scoring")

        with Vertical(id="scoring-config-dialog"):
            yield Label(title, id="config-title")
            yield Container(id="config-form", classes="form-container")
            with Horizontal(id="config-buttons"):
                yield Button("Guardar", variant="success", id="btn-save")
                yield Button("Restaurar", id="btn-reset")
                yield Button("Cancelar", variant="error", id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self._build_form()

    def _build_form(self) -> None:
        form = self.query_one("#config-form")
        
        form.remove_children()
        
        for child in list(form.children):
            child.remove()
        
        self._input_refs = {}

        config = load_scoring()

        if self.scoring_type == "mixed":
            self._build_weight_config(form, config, "mixed")
        elif self.scoring_type == "weighted":
            self._build_weight_config(form, config, "weighted")
        elif self.scoring_type == "time":
            self._build_time_config(form, config)
        elif self.scoring_type == "genre":
            self._build_genre_config(form, config)

    def _build_weight_config(self, container: Container, config, scoring_type: str) -> None:
        prefix = f"scoring_{scoring_type}_"
        critics_val = str(getattr(config, f"{prefix}critics", 0.3) * 100)
        users_val = str(getattr(config, f"{prefix}users", 0.5) * 100)
        duration_val = str(getattr(config, f"{prefix}duration", 0.2) * 100)

        container.mount(Label("Críticos (%)"))
        input_critics = Input(value=critics_val)
        container.mount(input_critics)
        self._input_refs["critics"] = input_critics

        container.mount(Label("Usuarios (%)"))
        input_users = Input(value=users_val)
        container.mount(input_users)
        self._input_refs["users"] = input_users

        container.mount(Label("Duración (%)"))
        input_duration = Input(value=duration_val)
        container.mount(input_duration)
        self._input_refs["duration"] = input_duration

        sum_label = Label("")
        container.mount(sum_label)
        self._input_refs["sum_label"] = sum_label
        self._update_sum_label()

    def _build_time_config(self, container: Container, config) -> None:
        hours = config.scoring_available_hours or DEFAULT_AVAILABLE_HOURS
        container.mount(Label("Horas disponibles"))
        input_hours = Input(value=str(hours))
        container.mount(input_hours)
        self._input_refs["hours"] = input_hours
        container.mount(Label("Los juegos con duración menor o igual obtendrán mejor puntuación."))

    def _build_genre_config(self, container: Container, config) -> None:
        from puntueitor.core.cachers.igdb_cacher import IGDBCacher
        import re

        cacher = IGDBCacher(paths.main_db())
        genres = cacher.get_all_genres()
        preferred = set(config.scoring_preferred_genres or [])

        container.mount(Label("Selecciona tus géneros preferidos:"))

        scroll = ScrollableContainer(id="genre-scroll")
        container.mount(scroll)
        self._input_refs["scroll"] = scroll

        self._input_refs["checkboxes"] = []

        for genre in genres:
            checkbox = Checkbox(genre, value=genre in preferred)
            scroll.mount(checkbox)
            self._input_refs["checkboxes"].append(checkbox)

        if not genres:
            scroll.mount(Label("No hay géneros disponibles. Carga la biblioteca primero."))

    def _update_sum_label(self) -> None:
        if "sum_label" not in self._input_refs:
            return
        try:
            c = float(self._input_refs["critics"].value or "0")
            u = float(self._input_refs["users"].value or "0")
            d = float(self._input_refs["duration"].value or "0")
            total = c + u + d
            label = self._input_refs["sum_label"]
            if abs(total - 100) < 0.1:
                label.update(f"✓ Suma: {total}%")
                label.styles.color = "green"
            else:
                label.update(f"⚠ Suma: {total}% (debe ser 100)")
                label.styles.color = "red"
        except ValueError:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input in (self._input_refs.get("critics"), self._input_refs.get("users"), self._input_refs.get("duration")):
            self._update_sum_label()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-reset":
            self._reset_to_defaults()
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def _validate_weights(self) -> bool:
        try:
            c = float(self._input_refs.get("critics", Input()).value or "0")
            u = float(self._input_refs.get("users", Input()).value or "0")
            d = float(self._input_refs.get("duration", Input()).value or "0")
            total = c + u + d
            if abs(total - 100) > 0.1:
                self.app.notify("La suma debe ser 100%", severity="error")
                return False
            return True
        except (ValueError, AttributeError):
            self.app.notify("Valores inválidos", severity="error")
            return False

    def _save_config(self) -> None:
        if self.scoring_type in ("mixed", "weighted") and not self._validate_weights():
            return

        config = load_scoring()

        if self.scoring_type == "mixed":
            config.scoring_mixed_critics = float(self._input_refs["critics"].value) / 100
            config.scoring_mixed_users = float(self._input_refs["users"].value) / 100
            config.scoring_mixed_duration = float(self._input_refs["duration"].value) / 100
        elif self.scoring_type == "weighted":
            config.scoring_weighted_critics = float(self._input_refs["critics"].value) / 100
            config.scoring_weighted_users = float(self._input_refs["users"].value) / 100
            config.scoring_weighted_duration = float(self._input_refs["duration"].value) / 100
        elif self.scoring_type == "time":
            try:
                config.scoring_available_hours = float(self._input_refs["hours"].value)
            except (ValueError, KeyError):
                config.scoring_available_hours = DEFAULT_AVAILABLE_HOURS
        elif self.scoring_type == "genre":
            selected = []
            checkboxes = self._input_refs.get("checkboxes", [])
            for cb in checkboxes:
                if cb.value:
                    selected.append(cb.label.plain)
            config.scoring_preferred_genres = selected

        save_scoring(config)
        self.app.notify("Configuración guardada.", severity="information")
        self.dismiss({"type": self.scoring_type})

    def _reset_to_defaults(self) -> None:
        config = load_scoring()

        if self.scoring_type == "mixed":
            config.scoring_mixed_critics = DEFAULT_MIXED_WEIGHTS["critics"]
            config.scoring_mixed_users = DEFAULT_MIXED_WEIGHTS["users"]
            config.scoring_mixed_duration = DEFAULT_MIXED_WEIGHTS["duration"]
        elif self.scoring_type == "weighted":
            config.scoring_weighted_critics = DEFAULT_WEIGHTED_WEIGHTS["critics"]
            config.scoring_weighted_users = DEFAULT_WEIGHTED_WEIGHTS["users"]
            config.scoring_weighted_duration = DEFAULT_WEIGHTED_WEIGHTS["duration"]
        elif self.scoring_type == "time":
            config.scoring_available_hours = DEFAULT_AVAILABLE_HOURS
        elif self.scoring_type == "genre":
            config.scoring_preferred_genres = []

        save_scoring(config)
        self._build_form()
        self.app.notify("Valores restaurados.", severity="information")

    def action_cancel(self) -> None:
        self.dismiss(None)