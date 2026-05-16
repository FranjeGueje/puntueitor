from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Markdown

from puntueitor.core.models import Game

class GameDetail(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Markdown("Selecciona un juego de la lista para ver sus detalles.", id="game-info")

    def show_game(self, game: Game):
        md = self.query_one("#game-info", Markdown)
        
        genres = ", ".join(game.genres) if game.genres else "Desconocido"
        duration = f"{game.duration_hours}h" if game.duration_hours is not None and game.duration_hours > 0 else "N/A"
        user_score = f"{game.user_score:.0f}/100" if game.user_score is not None else "N/A"
        critic_score = f"{game.critic_score:.0f}/100" if game.critic_score is not None else "N/A"
        storyline = game.storyline if game.storyline else "Sin descripción disponible."
        stores_list = ", ".join(game.stores.keys()) if game.stores else "Ninguna"

        content = f"""# {game.title}

**Géneros:** {genres}

**Duración:** {duration}

**Puntuación Usuario:** {user_score}

**Puntuación Crítica:** {critic_score}

**Tiendas:** {stores_list}

---

{storyline}
"""
        md.update(content)
