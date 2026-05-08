from textual.widgets import OptionList, Static
from textual.containers import Vertical
from textual.widgets.option_list import Option
from textual.message import Message
from textual import on

from puntueitor.core.models import Library, Game


class GameList(Vertical):
    class GameSelected(Message):
        def __init__(self, game: Game):
            self.game = game
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.games_map: dict[str, Game] = {}

    def compose(self):
        yield Static("Biblioteca: 0 juegos", id="game-count")
        yield OptionList(id="game-options")

    def populate_games(self, library: Library):
        option_list = self.query_one("#game-options", OptionList)
        count_label = self.query_one("#game-count", Static)
        
        option_list.clear_options()
        self.games_map.clear()

        count = len(library.games)
        count_label.update(f"Biblioteca: {count} juegos")

        if count == 0:
            option_list.add_option(Option("Biblioteca vacía", id="empty", disabled=True))
            return

        for game in library.games:
            opt_id = f"game_{game.igdb_id}"
            self.games_map[opt_id] = game
            option_list.add_option(Option(game.title, id=opt_id))
            
    @on(OptionList.OptionSelected, "#game-options")
    def on_game_selected(self, event: OptionList.OptionSelected):
        opt_id = event.option_id
        if opt_id and opt_id in self.games_map:
            self.post_message(self.GameSelected(self.games_map[opt_id]))

    def select_first(self):
        option_list = self.query_one("#game-options", OptionList)
        if option_list.option_count > 0:
            option_list.highlighted = 0
            option_list.focus()
            
            # Si hay un juego real, disparamos la selección para que se vean los detalles
            opt = option_list.get_option_at_index(0)
            if opt.id and opt.id in self.games_map:
                self.post_message(self.GameSelected(self.games_map[opt.id]))


