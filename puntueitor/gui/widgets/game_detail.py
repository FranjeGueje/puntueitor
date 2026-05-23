from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Markdown

from puntueitor.core.models import Game

REVIEW_LABELS = {
    0: "Sin análisis de usuarios",
    1: "Extremadamente negativas",
    2: "Muy negativas",
    3: "Negativas",
    4: "Mayormente negativas",
    5: "Variadas",
    6: "Mayormente positivas",
    7: "Positivas",
    8: "Muy positivas",
    9: "Extremadamente positivas",
}

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
        release = game.release_date.strftime("%d/%m/%Y") if game.release_date else "N/A"
        cover = f"[{game.cover_url}]({game.cover_url})" if game.cover_url else "N/A"
        steamdb_score_str = f"{game.steamdb_score:.2f}" if game.steamdb_score is not None else "N/A"
        if game.review_pos is not None and game.review_neg is not None:
            total = game.review_pos + game.review_neg
            steam_review_str = f"{REVIEW_LABELS.get(game.steam_review, 'N/A')} ({game.review_pos:,} positivas de {total:,} totales)".replace(",", ".")
        else:
            steam_review_str = REVIEW_LABELS.get(game.steam_review, "N/A")

        content = f"""# {game.title}

**🎮 Géneros:** {genres}

**⏱️ Duración:** {duration}

**⭐ Puntuación Usuario:** {user_score}

**🏆 Puntuación Crítica:** {critic_score}

**👍 Puntuación SteamDB:** {steamdb_score_str}             \\*Formula avanzada en base a puntuaciones de Steam

**🔥 Puntuación Steam:** {steam_review_str}

**🏪 Tiendas:** {stores_list}

**📅 Lanzamiento:** {release}

**🖼️ Carátula:** {cover}

---

{storyline}
"""
        md.update(content)
