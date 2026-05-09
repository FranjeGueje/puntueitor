from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal, Center, Middle, Container
from textual.widgets import Label, Static, Footer, ListItem, ListView
from textual import on

SCORING_INFO = {
    "weighted": {
        "title": "Weighted Score (El \"Equilibrado\")",
        "desc": (
            "Es un promedio tradicional. Su filosofía es la previsibilidad.\n\n"
            "Notas: Da el mismo valor a lo que dice la prensa (Crítica) que a lo que dicen los jugadores (Usuarios) (40% cada uno).\n"
            "Duración: Usa una caída lineal. Hasta las 15h el juego puntúa al máximo en este apartado, y a partir de ahí va perdiendo puntos de forma constante hasta llegar a las 60h, donde la puntuación por duración es cero.\n"
            "Para quién es: Para el usuario que quiere un ranking justo y proporcional donde cada hora extra de duración resta exactamente lo mismo.\n\n"
            "Si quieres ver tu lista ordenada de forma \"clásica\", usa Weighted."
        )
    },
    "mixed": {
        "title": "Mixed Score (El \"Recomendador Inteligente\")",
        "desc": (
            "Es un algoritmo con opinión propia, diseñado para destacar \"joyas\" que respeten tu tiempo.\n\n"
            "Notas: Se fía más de los usuarios (50%) que de los críticos (30%). Prioriza lo que le gusta a la gente real.\n"
            "Duración: Usa una curva exponencial. En lugar de restar puntos de forma constante, penaliza mucho más rápido los juegos que empiezan a ser largos. Un juego de 40h se verá mucho más \"castigado\" aquí que en el Weighted, porque el algoritmo asume que cuanto más largo es un juego, más difícil es que mantenga tu interés o que lo termines.\n"
            "Para quién es: Para el usuario que tiene muchos juegos pendientes (backlog) y quiere que el sistema le recomiende lo mejor de lo mejor, pero dándole un \"empujón\" extra a los juegos que son intensos y de duración razonable.\n\n"
            "Si quieres que Puntueitor te sugiera qué jugar hoy mismo priorizando juegos aclamados y no demasiado largos, usa Mixed."
        )
    },
    "time": {
        "title": "Available Time (El \"Planificador\")",
        "desc": (
            "Este sistema no mira si el juego es bueno o malo, sino si encaja en tu agenda.\n\n"
            "Cómo funciona: Toma las \"horas disponibles\" que hayas configurado (por defecto 20h) y compara la duración del juego.\n"
            "Resultado: Los juegos que duran menos que tu tiempo disponible obtienen la mejor puntuación. Los que se pasan empiezan a recibir penalizaciones.\n"
            "Para quién es: Para cuando tienes, por ejemplo, un fin de semana libre y quieres ver qué juegos de tu biblioteca podrías terminarte en ese tiempo."
        )
    },
    "genre": {
        "title": "Genre Match (El \"Personalizador\")",
        "desc": (
            "Este es el sistema más subjetivo, basado puramente en tus gustos.\n\n"
            "Cómo funciona: Mira los géneros del juego y los compara con tus \"Géneros Preferidos\" y \"Géneros Odiados\".\n"
            "Resultado: Sube la nota de los juegos que coinciden con lo que te gusta y hunde los juegos que tienen géneros que no soportas.\n"
            "Para quién es: Para filtrar el ruido. Si te encantan los RPG pero odias los Sports, este sistema pondrá todos tus RPGs arriba del todo, independientemente de si tienen un 90 o un 70 de nota."
        )
    }
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
        self.notify("Configuración no implementada todavía", severity="information")

    def action_cancel(self) -> None:
        self.dismiss(None)
