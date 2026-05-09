from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Container, ScrollableContainer
from textual.widgets import Label, Input, Button, Checkbox, Footer
from textual import on

from puntueitor.core.config import ConfigManager, DEFAULT_MIXED_WEIGHTS, DEFAULT_WEIGHTED_WEIGHTS, DEFAULT_AVAILABLE_HOURS


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

    def compose(self) -> ComposeResult:
        title = self.TITLES.get(self.scoring_type, "Configurar Scoring")

        with Vertical(id="scoring-config-dialog"):
            yield Label(title, id="config-title")
            yield Container(id="config-form")
            with Vertical(id="config-buttons"):
                yield Button("Guardar", variant="success", id="btn-save")
                yield Button("Restaurar valores por defecto", id="btn-reset")
                yield Button("Cancelar", variant="error", id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self._show_config_for_type()

    def _show_config_for_type(self) -> None:
        form = self.query_one("#config-form", Container)
        for widget in list(form.children):
            widget.remove()

        config = ConfigManager().get

        if self.scoring_type == "mixed":
            self._build_weight_config(form, config, "scoring_mixed_")
        elif self.scoring_type == "weighted":
            self._build_weight_config(form, config, "scoring_weighted_")
        elif self.scoring_type == "time":
            self._build_time_config(form, config)
        elif self.scoring_type == "genre":
            self._build_genre_config(form, config)

    def _build_weight_config(self, container: Container, config, prefix: str) -> None:
        critics_val = str(getattr(config, f"{prefix}critics", 0.3) * 100)
        users_val = str(getattr(config, f"{prefix}users", 0.5) * 100)
        duration_val = str(getattr(config, f"{prefix}duration", 0.2) * 100)

        container.mount(Label("Críticos (%)"))
        container.mount(Input(value=critics_val, id="input-critics"))
        container.mount(Label("Usuarios (%)"))
        container.mount(Input(value=users_val, id="input-users"))
        container.mount(Label("Duración (%)"))
        container.mount(Input(value=duration_val, id="input-duration"))
        container.mount(Label("", id="sum-label"))
        self._update_sum_label()

    def _build_time_config(self, container: Container, config) -> None:
        hours = config.scoring_available_hours or DEFAULT_AVAILABLE_HOURS
        container.mount(Label("Horas disponibles"))
        container.mount(Input(value=str(hours), id="input-hours"))
        container.mount(Label("Los juegos con duración menor o igual obtendrán mejor puntuación."))

    def _build_genre_config(self, container: Container, config) -> None:
        from puntueitor.core.cachers.igdb_cacher import IGDBCacher
        import re

        cacher = IGDBCacher("cache/igdb.sqlite")
        genres = cacher.get_all_genres()
        preferred = set(config.scoring_preferred_genres or [])

        container.mount(Label("Selecciona tus géneros preferidos:"))

        scroll = ScrollableContainer(id="genre-scroll")
        container.mount(scroll)

        for genre in genres:
            safe_id = re.sub(r'[^a-zA-Z0-9_]', '_', genre)
            checkbox = Checkbox(genre, id=f"genre-{safe_id}", value=genre in preferred)
            scroll.mount(checkbox)

        if not genres:
            scroll.mount(Label("No hay géneros disponibles. Carga la biblioteca primero."))

    def _update_sum_label(self) -> None:
        try:
            c = float(self.query_one("#input-critics", Input).value or "0")
            u = float(self.query_one("#input-users", Input).value or "0")
            d = float(self.query_one("#input-duration", Input).value or "0")
            total = c + u + d
            label = self.query_one("#sum-label", Label)
            if abs(total - 100) < 0.1:
                label.update(f"✓ Suma: {total}%")
                label.styles.color = "green"
            else:
                label.update(f"⚠ Suma: {total}% (debe ser 100)")
                label.styles.color = "red"
        except ValueError:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in ("input-critics", "input-users", "input-duration"):
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
            c = float(self.query_one("#input-critics", Input).value or "0")
            u = float(self.query_one("#input-users", Input).value or "0")
            d = float(self.query_one("#input-duration", Input).value or "0")
            total = c + u + d
            if abs(total - 100) > 0.1:
                self.app.notify("La suma debe ser 100%", severity="error")
                return False
            return True
        except ValueError:
            self.app.notify("Valores inválidos", severity="error")
            return False

    def _save_config(self) -> None:
        if self.scoring_type in ("mixed", "weighted") and not self._validate_weights():
            return

        manager = ConfigManager()
        config = manager.get

        if self.scoring_type == "mixed":
            config.scoring_mixed_critics = float(self.query_one("#input-critics", Input).value) / 100
            config.scoring_mixed_users = float(self.query_one("#input-users", Input).value) / 100
            config.scoring_mixed_duration = float(self.query_one("#input-duration", Input).value) / 100
        elif self.scoring_type == "weighted":
            config.scoring_weighted_critics = float(self.query_one("#input-critics", Input).value) / 100
            config.scoring_weighted_users = float(self.query_one("#input-users", Input).value) / 100
            config.scoring_weighted_duration = float(self.query_one("#input-duration", Input).value) / 100
        elif self.scoring_type == "time":
            try:
                config.scoring_available_hours = float(self.query_one("#input-hours", Input).value)
            except ValueError:
                config.scoring_available_hours = DEFAULT_AVAILABLE_HOURS
        elif self.scoring_type == "genre":
            scroll = self.query_one("#genre-scroll")
            selected = []
            for child in scroll.children:
                if isinstance(child, Checkbox) and child.value:
                    selected.append(child.label.plain)
            config.scoring_preferred_genres = selected

        manager.save()
        self.app.notify("Configuración guardada.", severity="information")
        self.dismiss({"type": self.scoring_type})

    def _reset_to_defaults(self) -> None:
        manager = ConfigManager()
        config = manager.get

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

        manager.save()
        self._show_config_for_type()
        self.app.notify("Valores restaurados.", severity="information")

    def action_cancel(self) -> None:
        self.dismiss(None)