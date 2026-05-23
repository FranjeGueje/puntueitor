from textual.widgets import DataTable, Static
from textual.containers import Vertical
from textual.message import Message
from textual.content import Text
from textual import on

from puntueitor.core.models import Library, Game


class GameList(Vertical):
    class GameSelected(Message):
        def __init__(self, game: Game):
            self.game = game
            super().__init__()

    class GameHighlighted(Message):
        def __init__(self, game: Game):
            self.game = game
            super().__init__()

    class UnknownSelected(Message):
        def __init__(self, unknown: dict):
            self.unknown = unknown
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.games_map: dict[str, Game] = {}
        self.current_unknowns: list[dict] = []
        self.show_hidden = False

    def compose(self):
        yield Static("Biblioteca: 0 juegos", id="game-count")
        yield DataTable(id="game-options", cursor_type="row")

    def on_mount(self):
        table = self.query_one(DataTable)
        table.add_column("Título", key="title", width=70)
        table.add_column("U", key="user")
        table.add_column("C", key="critic")
        table.add_column("Dur", key="duration")
        table.add_column("Fin", key="finished", width=3)
        table.add_column("Bkl", key="backlog", width=3)
        table.add_column("Fav", key="favorite", width=3)

    def populate_games(self, library: Library, scores: dict[int, float] | None = None):
        table = self.query_one("#game-options", DataTable)
        count_label = self.query_one("#game-count", Static)
        
        try:
            current_row = table.cursor_row
        except:
            current_row = 0

        table.clear(columns=True)
        table.add_column("Título", key="title", width=70)
        table.add_column("U", key="user")
        table.add_column("C", key="critic")
        table.add_column("Dur", key="duration")
        if scores is not None:
            table.add_column("Puntos", key="score")
        table.add_column("Fin", key="finished", width=3)
        table.add_column("Bkl", key="backlog", width=3)
        table.add_column("Fav", key="favorite", width=3)

        self.games_map.clear()

        if self.show_hidden:
            visible_games = list(library.games)
            count = len(visible_games)
            count_label.update(f"Biblioteca: {count} juegos (mostrando ocultos)")
        else:
            visible_games = [g for g in library.games if not g.hidden]
            count = len(visible_games)
            hidden_count = len(library.games) - count
            count_text = f"Biblioteca: {count} juegos"
            if hidden_count:
                count_text += f" ({hidden_count} ocultos)"
            count_label.update(count_text)

        if count == 0:
            return

        for game in visible_games:
            row_key = str(game.igdb_id)
            self.games_map[row_key] = game

            # Formatear métricas
            if game.user_score is not None and game.user_score > 0:
                u = f"{game.user_score:.0f}"
            elif game.steamdb_score is not None and game.steamdb_score > 0:
                u = Text(f"{game.steamdb_score:.0f}", style="white on red")
            else:
                u = "--"
            c = f"{game.critic_score:.0f}" if game.critic_score is not None else "--"
            d = f"{game.duration_hours:.0f}h" if game.duration_hours is not None else "--"

            row_data = [game.title, u, c, d]
            if scores is not None:
                s = scores.get(game.igdb_id, 0.0)
                row_data.append(f"{s*100:.1f}")

            row_data.extend([
                "✓" if game.finished else "",
                "✓" if game.backlog else "",
                "✓" if game.favorite else "",
            ])

            table.add_row(*row_data, key=row_key)
        
        if table.row_count > current_row:
            table.move_cursor(row=current_row)
            
    @on(DataTable.RowSelected, "#game-options")
    def on_game_selected(self, event: DataTable.RowSelected):
        row_key = event.row_key.value
        if row_key and row_key in self.games_map:
            self.post_message(self.GameSelected(self.games_map[row_key]))
        elif row_key and row_key.startswith("unknown_"):
            idx = int(row_key.split("_")[1])
            if idx < len(self.current_unknowns):
                self.post_message(self.UnknownSelected(self.current_unknowns[idx]))

    @on(DataTable.RowHighlighted, "#game-options")
    def on_game_highlighted(self, event: DataTable.RowHighlighted):
        row_key = event.row_key.value
        if row_key and row_key in self.games_map:
            self.post_message(self.GameHighlighted(self.games_map[row_key]))

    def select_first(self):
        table = self.query_one("#game-options", DataTable)
        if table.row_count > 0:
            table.move_cursor(row=0)
            table.focus()

    def get_current_game(self) -> Game | None:
        table = self.query_one("#game-options", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return None
        row = table.ordered_rows[table.cursor_row]
        return self.games_map.get(str(row.key.value))

    def update_game(self, game: Game):
        """Actualiza la información de un juego en la lista sin recargarla entera."""
        row_key = str(game.igdb_id)
        self.games_map[row_key] = game
        
        table = self.query_one(DataTable)
        duration_str = f"{game.duration_hours:.0f}h" if game.duration_hours is not None else "--"
        
        if game.user_score is not None and game.user_score > 0:
            u = f"{game.user_score:.0f}"
        elif game.steamdb_score is not None and game.steamdb_score > 0:
            u = Text(f"{game.steamdb_score:.0f}", style="white on red")
        else:
            u = "--"
        try:
            table.update_cell(row_key, "user", u)
        except Exception:
            table.update_cell(row_key, 1, u)

        try:
            table.update_cell(row_key, "duration", duration_str)
        except Exception:
            table.update_cell(row_key, 3, duration_str)

        table.update_cell(row_key, "finished", "✓" if game.finished else "")
        table.update_cell(row_key, "backlog", "✓" if game.backlog else "")
        table.update_cell(row_key, "favorite", "✓" if game.favorite else "")

    def add_game_to_table(self, game: Game):
        """Añade un solo juego a la tabla sin limpiarla."""
        if not self.show_hidden and game.hidden:
            return
        table = self.query_one("#game-options", DataTable)
        row_key = str(game.igdb_id)
        self.games_map[row_key] = game
        
        if game.user_score is not None and game.user_score > 0:
            u = f"{game.user_score:.0f}"
        elif game.steamdb_score is not None and game.steamdb_score > 0:
            u = Text(f"{game.steamdb_score:.0f}", style="white on red")
        else:
            u = "--"
        c = f"{game.critic_score:.0f}" if game.critic_score is not None else "--"
        d = f"{game.duration_hours:.0f}h" if game.duration_hours is not None else "--"
        
        table.add_row(game.title, u, c, d,
            "✓" if game.finished else "",
            "✓" if game.backlog else "",
            "✓" if game.favorite else "",
            key=row_key)
        
        count_label = self.query_one("#game-count", Static)
        count_label.update(f"Biblioteca: {len(self.games_map)} juegos")

    def populate_unknowns(self, unknowns: list[dict]):
        table = self.query_one("#game-options", DataTable)
        count_label = self.query_one("#game-count", Static)

        table.clear(columns=True)
        table.add_column("Título", key="title", width=70)
        table.add_column("Tienda", key="store", width=10)
        table.add_column("ID", key="id", width=10)

        self.games_map.clear()
        self.current_unknowns = unknowns
        count_label.update(f"Desconocidos: {len(unknowns)} juegos")

        for i, u in enumerate(unknowns):
            table.add_row(u["title"], u["store"], u["id"], key=f"unknown_{i}")


