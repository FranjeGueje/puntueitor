from textual.widgets import DataTable, Static
from textual.containers import Vertical
from textual.message import Message
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.games_map: dict[str, Game] = {}

    def compose(self):
        yield Static("Biblioteca: 0 juegos", id="game-count")
        yield DataTable(id="game-options", cursor_type="row")

    def on_mount(self):
        table = self.query_one(DataTable)
        table.add_column("Título", key="title")
        table.add_column("U", key="user")
        table.add_column("C", key="critic")
        table.add_column("Dur", key="duration")

    def populate_games(self, library: Library, scores: dict[int, float] | None = None):
        table = self.query_one("#game-options", DataTable)
        count_label = self.query_one("#game-count", Static)
        
        # Guardar posición actual
        try:
            current_row = table.cursor_row
        except:
            current_row = 0

        table.clear()
        
        # Manejo de la columna Score
        has_score_col = any(col.key.value == "score" for col in table.columns.values())
        if scores is not None and not has_score_col:
            table.add_column("Puntos", key="score")
        elif scores is None and has_score_col:
            # Recreamos columnas sin score para limpiar
            table.clear(columns=True)
            table.add_column("Título", key="title")
            table.add_column("U", key="user")
            table.add_column("C", key="critic")
            table.add_column("Dur", key="duration")

        self.games_map.clear()
 
        count = len(library.games)
        count_label.update(f"Biblioteca: {count} juegos")
 
        if count == 0:
            return

        for game in library.games:
            row_key = str(game.igdb_id)
            self.games_map[row_key] = game
            
            # Formatear métricas
            u = f"{game.user_score:.0f}" if game.user_score is not None else "--"
            c = f"{game.critic_score:.0f}" if game.critic_score is not None else "--"
            d = f"{game.duration_hours:.0f}h" if game.duration_hours is not None else "--"
            
            row_data = [game.title, u, c, d]
            if scores is not None:
                s = scores.get(game.igdb_id, 0.0)
                # Si el rango es 0-1, lo mostramos como porcentaje o 0.xx
                # Pero como MixedScore era 0-100 y ahora lo estandarizamos,
                # mostramos 0-100 para que sea legible.
                row_data.append(f"{s*100:.1f}")
            
            table.add_row(*row_data, key=row_key)
        
        if table.row_count > current_row:
            table.move_cursor(row=current_row)
            
    @on(DataTable.RowSelected, "#game-options")
    def on_game_selected(self, event: DataTable.RowSelected):
        row_key = event.row_key.value
        if row_key and row_key in self.games_map:
            self.post_message(self.GameSelected(self.games_map[row_key]))

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
            
            # Si hay un juego real, disparamos la selección
            # Nota: move_cursor no dispara RowSelected automáticamente en algunas versiones
            row_key = table.get_row_at(0) # Esto no es correcto para obtener la key
            # En Textual, table.rows es un dict de RowKey: Row
            row_keys = list(table.rows.keys())
            if row_keys:
                first_key = row_keys[0].value
                if first_key in self.games_map:
                    self.post_message(self.GameSelected(self.games_map[first_key]))

    def update_game(self, game: Game):
        """Actualiza la información de un juego en la lista sin recargarla entera."""
        row_key = str(game.igdb_id)
        self.games_map[row_key] = game
        
        table = self.query_one(DataTable)
        duration_str = f"{game.duration_hours:.0f}h" if game.duration_hours is not None else "--"
        
        try:
            table.update_cell(row_key, "duration", duration_str)
        except Exception:
            # Si falla por clave, intentamos por índice (col 3)
            table.update_cell(row_key, 3, duration_str)

    def add_game_to_table(self, game: Game):
        """Añade un solo juego a la tabla sin limpiarla."""
        table = self.query_one("#game-options", DataTable)
        row_key = str(game.igdb_id)
        self.games_map[row_key] = game
        
        u = f"{game.user_score:.0f}" if game.user_score is not None else "--"
        c = f"{game.critic_score:.0f}" if game.critic_score is not None else "--"
        d = f"{game.duration_hours:.0f}h" if game.duration_hours is not None else "--"
        
        table.add_row(game.title, u, c, d, key=row_key)
        
        # Actualizar contador
        count_label = self.query_one("#game-count", Static)
        count_label.update(f"Biblioteca: {len(self.games_map)} juegos")


