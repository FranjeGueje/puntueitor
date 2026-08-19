"""
Qué tiendas se cargan. En el carrusel es Opciones → Tiendas.

Las credenciales y las sesiones se fueron a la pantalla de Cuentas (tecla
`a`): son otra cosa —con qué te identificas, no qué quieres ver— y se tocan
en otro momento. Por eso esta pantalla dejó de llamarse "Configuración": ya
no configura nada más que esto.
"""
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Label

from puntueitor.core import stores
from puntueitor.core.config import ConfigManager


class ConfigurationScreen(Screen):
    BINDINGS = [("escape", "cancel", "Cancelar")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle():
            with Center():
                with Vertical(id="config-dialog"):
                    yield Label("Tiendas a cargar", classes="section-title")
                    # Del registro (`core/stores/`): una tienda nueva aparece
                    # aquí sola, con su id derivado de su clave.
                    for spec in stores.all_stores():
                        yield Checkbox(spec.label, id=f"store-{spec.key}")

                    yield Label(
                        "Las credenciales y las sesiones están en Cuentas (a)",
                        classes="section-title",
                    )

                    with Horizontal(id="config-buttons"):
                        yield Button("Guardar", variant="success", id="btn-save")
                        yield Button("Cancelar", variant="error", id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Tiendas"
        config = ConfigManager().get

        for spec in stores.all_stores():
            self.query_one(f"#store-{spec.key}", Checkbox).value = getattr(
                config, spec.config_flag, False,
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self.action_save()
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_save(self) -> None:
        manager = ConfigManager()
        config = manager.get

        for spec in stores.all_stores():
            setattr(
                config, spec.config_flag,
                self.query_one(f"#store-{spec.key}", Checkbox).value,
            )

        manager.save()
        self.app.notify("Tiendas guardadas correctamente.", severity="information")
        self.dismiss()

    def action_cancel(self) -> None:
        self.dismiss()
