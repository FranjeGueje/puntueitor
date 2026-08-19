"""
Iniciar sesión en las tiendas desde la terminal.

Toda la lógica está en `core/services/accounts`; aquí solo se pinta y se
recogen dos cosas: el botón que abre el navegador y el texto que el usuario
pega al volver. El mismo servicio lo usa el carrusel, así que el flujo es
literalmente el mismo en las dos interfaces.
"""
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label

from puntueitor.core.models import Stores
from puntueitor.core.services import accounts

#: Qué se le dice al usuario que va a tener que pegar en cada tienda.
_QUE_PEGAR = {
    Stores.STEAM: "Pega la dirección a la que te lleva Steam al entrar",
    Stores.GOG: "Pega la dirección de la página en blanco a la que llegas",
    Stores.EPIC: "Pega el texto que sale en la página (o su dirección)",
    Stores.AMAZON: "Pega la dirección a la que te lleva Amazon al entrar",
}

_ETIQUETAS = {
    Stores.STEAM: "Steam",
    Stores.GOG: "GOG",
    Stores.EPIC: "Epic",
    Stores.AMAZON: "Amazon",
}


class AccountsScreen(Screen):
    """Una fila por tienda: estado, entrar, pegar y salir."""

    BINDINGS = [("escape", "cancel", "Volver")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle():
            with Center():
                with Vertical(id="accounts-dialog"):
                    yield Label(
                        "Puntueitor abre el navegador; al terminar de entrar, "
                        "copia la dirección de la barra y pégala aquí.",
                        classes="section-title",
                    )
                    for store in Stores:
                        yield from self._fila(store)
                    yield Button("Volver", id="btn-close")
        yield Footer()

    def _fila(self, store: Stores) -> ComposeResult:
        nombre = _ETIQUETAS[store]
        yield Label(nombre, classes="section-title")
        yield Label(self._estado(store), id=f"estado-{store}")
        yield Input(id=f"pegado-{store}", placeholder=_QUE_PEGAR[store])
        with Horizontal():
            yield Button("Abrir navegador", id=f"abrir-{store}")
            yield Button("Guardar lo pegado", variant="success", id=f"pegar-{store}")
            yield Button("Cerrar sesión", variant="error", id=f"salir-{store}")

    @staticmethod
    def _estado(store: Stores) -> str:
        if store == Stores.STEAM:
            return (
                "Configurada" if accounts.has_session(store)
                else "Falta la API key o el Steam ID (Configuración)"
            )
        return "Sesión iniciada" if accounts.has_session(store) else "Sin sesión"

    def on_mount(self) -> None:
        self.title = "Cuentas"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        boton = event.button.id or ""
        if boton == "btn-close":
            self.dismiss()
            return

        accion, _, store = boton.partition("-")
        if not store:
            return

        if accion == "abrir":
            resultado = accounts.open_login(store)
        elif accion == "pegar":
            campo = self.query_one(f"#pegado-{store}", Input)
            resultado = accounts.finish_login(store, campo.value)
            if resultado.ok:
                # El código pegado no vale para nada dos veces y es lo más
                # sensible que hay en pantalla: fuera en cuanto se canjea.
                campo.value = ""
        elif accion == "salir":
            resultado = accounts.logout(store)
        else:
            return

        self.query_one(f"#estado-{store}", Label).update(self._estado(store))
        # En la terminal la dirección SÍ se puede enseñar entera y copiar con
        # el ratón, así que se enseña: es la salida cuando no hay navegador.
        mensaje = (
            f"{resultado.mensaje}\n{resultado.url}"
            if resultado.url else resultado.mensaje
        )
        self.app.notify(
            mensaje,
            severity="information" if resultado.ok else "error",
            timeout=15,
        )

    def action_cancel(self) -> None:
        self.dismiss()
