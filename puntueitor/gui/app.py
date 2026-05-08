import os
import glob
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, LoadingIndicator, Label
from textual.containers import Horizontal, Center, Middle, Vertical
from textual import work

from puntueitor.gui.widgets.game_list import GameList
from puntueitor.gui.widgets.game_detail import GameDetail
from puntueitor.gui.screens.configuration import ConfigurationScreen
from puntueitor.gui.screens.quit_confirmation import QuitConfirmation
from puntueitor.gui.screens.sorting import SortingScreen
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.models import Library
from puntueitor.core.scoring.mixed_score import MixedScore
from puntueitor.core.models.scoring_context import ScoringContext

from puntueitor.core.config import ConfigManager
from puntueitor.core.igdb.service import IGDBService
from puntueitor.core.pipeline.load_steam_library import load_steam_library

class PuntueitorApp(App):
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("q", "request_quit", "Salir"),
        ("c", "configure", "Configurar"),
        ("s", "sort_library", "Ordenar"),
        ("r", "soft_reload", "Actualizar"),
        ("R", "reload_library", "Regenerar TODO"),
    ]


    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield GameList(id="game-list")
            yield GameDetail(id="game-detail")

        with Center(id="loading-container"):
            with Middle():
                with Vertical(id="loading-box"):
                    yield LoadingIndicator(id="spinner")
                    yield Label("Preparando recarga...", id="loading-title")
                    yield Label("", id="loading-counter")
                    yield Label("", id="loading-game-name")

        yield Footer()

    def on_mount(self) -> None:
        self.title = "Puntueitor"
        self.current_library = Library.from_iterable(())
        game_list = self.query_one(GameList)


        config = ConfigManager().get
        missing = []
        if not config.steam_api_key:
            missing.append("Steam API Key")
        if not config.steam_user_id:
            missing.append("Steam User ID")
        if not config.igdb_client_id:
            missing.append("IGDB Client ID")
        if not config.igdb_client_secret:
            missing.append("IGDB Client Secret")

        if missing:
            self.notify(
                f"Configuración incompleta. Presiona 'c' para configurar. Faltan: {', '.join(missing)}",
                severity="warning"
            )

        try:
            repo = LibraryRepository()
            self.current_library = repo.load()
            game_list.populate_games(self.current_library)
            game_list.select_first()


            old_path = "cache/library.json"
            if os.path.exists(old_path):
                os.remove(old_path)
        except Exception as e:
            game_list.populate_games(Library.from_iterable(()))
            self.notify(f"Error cargando librería: {e}", severity="error")

    def on_game_list_game_selected(self, message: GameList.GameSelected) -> None:
        detail = self.query_one(GameDetail)
        detail.show_game(message.game)

    def action_configure(self) -> None:
        self.push_screen(ConfigurationScreen())

    def action_request_quit(self) -> None:
        def check_quit(should_quit: bool) -> None:
            if should_quit:
                self.exit()
        
        self.push_screen(QuitConfirmation(), check_quit)

    def action_sort_library(self) -> None:
        def handle_sorting(criteria: str | None) -> None:
            if criteria:
                self.apply_sorting(criteria)
        
        self.push_screen(SortingScreen(), handle_sorting)

    def apply_sorting(self, criteria: str) -> None:
        games = list(self.current_library.games)
        
        if criteria == "title":
            games.sort(key=lambda g: g.title.lower())
        elif criteria == "user_score":
            games.sort(key=lambda g: g.user_score or 0.0, reverse=True)
        elif criteria == "critic_score":
            games.sort(key=lambda g: g.critic_score or 0.0, reverse=True)
        elif criteria == "duration":
            # Más cortos primero, pero si es None (desconocido) al final
            games.sort(key=lambda g: g.duration_hours if g.duration_hours is not None else 9999.0)
        elif criteria == "mixed":
            strategy = MixedScore()
            ctx = ScoringContext()
            games.sort(key=lambda g: strategy.score(g, ctx), reverse=True)

        self.current_library = Library.from_iterable(games)
        game_list = self.query_one(GameList)
        game_list.populate_games(self.current_library)
        game_list.select_first()
        self.notify(f"Biblioteca ordenada por: {criteria}")

    def _check_config(self) -> bool:
        config = ConfigManager().get
        if not all([config.steam_api_key, config.steam_user_id, config.igdb_client_id, config.igdb_client_secret]):
            self.notify("Error: Configuración incompleta. Faltan credenciales de Steam o IGDB.", severity="error")
            return False
        return True

    def _show_loading(self, title: str) -> None:
        self.query_one("#main-container").styles.display = "none"
        self.query_one("#loading-container").add_class("active")
        self.query_one("#loading-title", Label).update(title)
        self.query_one("#loading-counter", Label).update("")
        self.query_one("#loading-game-name", Label).update("")

    def action_soft_reload(self) -> None:
        """r: actualiza tiendas desde API y añade solo juegos nuevos a resolvers/igdb."""
        if not self._check_config():
            return
        self._show_loading("Actualizando tiendas... (solo juegos nuevos)")
        self.do_reload(refresh=False, force_store_refresh=True)

    def action_reload_library(self) -> None:
        """R: borra toda la caché SQLite y recarga todo desde cero."""
        if not self._check_config():
            return
        self._show_loading("Borrando caché y recargando todo desde cero...")
        self.do_reload(refresh=True, force_store_refresh=True)

    @work(thread=True)
    def do_reload(self, refresh: bool = False, force_store_refresh: bool = False) -> None:
        def progress(current: int, total: int, name: str) -> None:
            self.call_from_thread(self._update_progress, current, total, name)

        try:
            if refresh:
                # Borrar todas las DBs de caché SQLite (locales y de usuario)
                for db_file in glob.glob("cache/*.sqlite"):
                    os.remove(db_file)
                
                user_cache_dir = Path.home() / ".cache" / "puntueitor"
                if user_cache_dir.exists():
                    for db_file in glob.glob(str(user_cache_dir / "*.sqlite")):
                        os.remove(db_file)

            igdb_service = IGDBService()
            library = load_steam_library(
                engine=igdb_service,
                refresh=refresh,
                force_store_refresh=force_store_refresh,
                progress_callback=progress,
            )

            repo = LibraryRepository()
            repo.save(library)

            self.current_library = library
            self.call_from_thread(self._finish_reload, library, refresh)

        except Exception as e:
            self.call_from_thread(self._handle_reload_error, str(e))

    def _finish_reload(self, library: Library, refresh: bool = False) -> None:
        self.query_one("#loading-container").remove_class("active")
        self.query_one("#main-container").styles.display = "block"
        game_list = self.query_one(GameList)
        game_list.populate_games(library)
        game_list.select_first()
        msg = "¡Biblioteca recargada desde cero!" if refresh else f"¡Biblioteca actualizada! ({len(library.games)} juegos)"
        self.notify(msg, severity="information")

    def _handle_reload_error(self, error_msg: str) -> None:
        self.query_one("#loading-container").remove_class("active")
        self.query_one("#main-container").styles.display = "block"
        self.notify(f"Fallo al recargar: {error_msg}", severity="error")

    def _update_progress(self, current: int, total: int, name: str) -> None:
        self.query_one("#loading-title", Label).update("Cargando juegos desde IGDB...")
        self.query_one("#loading-counter", Label).update(f"{current} / {total} juegos")
        short_name = name[:50] + "..." if len(name) > 50 else name
        self.query_one("#loading-game-name", Label).update(f"[ {short_name} ]")

if __name__ == "__main__":
    app = PuntueitorApp()
    app.run()
