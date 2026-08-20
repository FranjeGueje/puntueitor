"""
Con qué se identifica Puntueitor ante cada servicio.

Junta las tres cosas que antes estaban repartidas entre dos pantallas y son
la misma: las credenciales de IGDB, las de Steam y las sesiones de las
tiendas que sí tienen login. Lo que se carga —qué tiendas— se queda en
Tiendas, que es otra decisión y se toma en otro momento.

Steam sale como CAMPOS DE TEXTO y no como una fila de conectar: no tiene
OAuth para terceros, y enseñarlo igual que a GOG haría creer que entrando por
el navegador se acaba el trabajo, cuando la API key hay que sacarla a mano de
la web de Valve de todas formas.

La lógica de las sesiones está en `core/services/accounts`; aquí solo se
pinta y se recogen dos cosas: el botón que abre el navegador y el texto que
el usuario pega al volver. El mismo servicio lo usa el carrusel, así que el
flujo es literalmente el mismo en las dos interfaces.
"""
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label

from puntueitor.core import stores
from puntueitor.core.config import ConfigManager
from puntueitor.core.services import accounts



class AccountsScreen(Screen):
    """Credenciales arriba, tiendas con sesión abajo."""

    BINDINGS = [("escape", "cancel", "Volver")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle():
            with Center():
                with Vertical(id="accounts-dialog"):
                    yield Label("IGDB", classes="section-title")
                    yield Label("Client ID")
                    yield Input(id="igdb-client-id")
                    yield Label("Client Secret")
                    yield Input(password=True, id="igdb-client-secret")

                    yield Label("Steam", classes="section-title")
                    yield Label("Steam User ID (numérico)")
                    yield Input(id="steam-user-id", type="number")
                    yield Label(
                        "API Key (steamcommunity.com/dev/apikey)"
                    )
                    yield Input(password=True, id="steam-api-key")

                    yield Label("itch.io", classes="section-title")
                    yield Label(
                        "Client ID (itch.io/user/settings/oauth-apps)"
                    )
                    yield Input(id="itchio-client-id")

                    yield Label(
                        "Tiendas: Puntueitor abre el navegador; al terminar "
                        "de entrar, copia la dirección de la barra y pégala.",
                        classes="section-title",
                    )
                    for spec in stores.with_session():
                        yield from self._fila(spec)

                    with Horizontal(id="accounts-buttons"):
                        yield Button("Guardar", variant="success", id="btn-save")
                        yield Button("Volver", id="btn-close")
        yield Footer()

    def _fila(self, spec) -> ComposeResult:
        """La fila de una tienda, sacada de lo que declara en el registro."""
        store = spec.key
        yield Label(spec.label, classes="section-title")
        yield Label(self._estado(store), id=f"estado-{store}")
        yield Input(id=f"pegado-{store}", placeholder=spec.paste_hint)
        with Horizontal():
            yield Button("Abrir navegador", id=f"abrir-{store}")
            yield Button("Guardar lo pegado", variant="success", id=f"pegar-{store}")
            yield Button("Cerrar sesión", variant="error", id=f"salir-{store}")

    @staticmethod
    def _estado(store: str) -> str:
        return "Sesión iniciada" if accounts.has_session(store) else "Sin sesión"

    def on_mount(self) -> None:
        self.title = "Cuentas"
        config = ConfigManager().get
        self.query_one("#igdb-client-id", Input).value = config.igdb_client_id or ""
        self.query_one("#igdb-client-secret", Input).value = (
            config.igdb_client_secret or ""
        )
        self.query_one("#steam-api-key", Input).value = config.steam_api_key or ""
        self.query_one("#steam-user-id", Input).value = (
            str(config.steam_user_id) if config.steam_user_id else ""
        )
        self.query_one("#itchio-client-id", Input).value = (
            config.itchio_client_id or ""
        )

    # ──────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        boton = event.button.id or ""
        if boton == "btn-close":
            self.dismiss()
            return
        if boton == "btn-save":
            self._save()
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

    def _save(self) -> None:
        """
        Guarda las credenciales.

        Las sesiones no se guardan aquí: se guardan solas al iniciarlas, que
        es cuando llega el token. Este botón es solo para lo que se teclea.
        """
        manager = ConfigManager()
        config = manager.get

        config.igdb_client_id = self.query_one("#igdb-client-id", Input).value
        config.igdb_client_secret = self.query_one(
            "#igdb-client-secret", Input
        ).value
        config.steam_api_key = self.query_one("#steam-api-key", Input).value
        config.itchio_client_id = self.query_one("#itchio-client-id", Input).value

        user_id = self.query_one("#steam-user-id", Input).value
        try:
            config.steam_user_id = int(user_id) if user_id else 0
        except ValueError:
            config.steam_user_id = 0

        manager.save()
        self.app.notify("Credenciales guardadas.", severity="information")

    def action_cancel(self) -> None:
        self.dismiss()
