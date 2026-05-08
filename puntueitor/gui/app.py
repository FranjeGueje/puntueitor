import os
import glob
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, LoadingIndicator, Label, ProgressBar
from textual.containers import Horizontal, Center, Middle, Vertical, Container
from textual import work

from puntueitor.gui.widgets.game_list import GameList
from puntueitor.gui.widgets.game_detail import GameDetail
from puntueitor.gui.screens.configuration import ConfigurationScreen
from puntueitor.gui.screens.quit_confirmation import QuitConfirmation
from puntueitor.gui.screens.sorting import SortingScreen
from puntueitor.gui.screens.filtering import FilteringScreen
from puntueitor.gui.screens.filter_input import FilterInputScreen
from puntueitor.gui.screens.enrichers import EnrichersScreen
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.models import Library, Game
from puntueitor.core.scoring.mixed_score import MixedScore
from puntueitor.core.models.scoring_context import ScoringContext

from puntueitor.core.config import ConfigManager
from puntueitor.core.igdb.service import IGDBService
from puntueitor.core.pipeline.load_steam_library import load_steam_library
from puntueitor.core.filters import NameFilter, DurationFilter

class PuntueitorApp(App):
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("q", "request_quit", "Salir"),
        ("c", "configure", "Configurar"),
        ("s", "sort_library", "Ordenar"),
        ("f", "filter_library", "Filtrar"),
        ("e", "enrich_library", "Enriquecer"),
        ("r", "soft_reload", "Actualizar"),
        ("R", "reload_library", "Regenerar TODO"),
    ]


    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield GameList(id="game-list")
            yield GameDetail(id="game-detail")

        with Horizontal(id="status-bar"):
            yield Label("Listo", id="status-message")
            yield ProgressBar(total=100, id="status-progress", show_eta=False)

        yield Footer()

    def on_mount(self) -> None:
        self.title = "Puntueitor"
        self.full_library = Library.from_iterable(())
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
            self.repo = LibraryRepository()
            self.full_library = self.repo.load()
            self.current_library = self.full_library
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
        def handle_sorting(result: tuple[str, bool] | None) -> None:
            if result:
                criteria, reverse = result
                self.apply_sorting(criteria, reverse)
        
        self.push_screen(SortingScreen(), handle_sorting)

    def action_filter_library(self) -> None:
        def handle_filter_type(filter_type: str | None) -> None:
            if filter_type == "clear":
                self.apply_filter(None)
            elif filter_type == "name":
                self.push_screen(
                    FilterInputScreen("Filtrar por nombre", "Introduce el nombre del juego..."),
                    lambda val: self.apply_filter("name", val) if val is not None else None
                )
            elif filter_type == "duration":
                self.push_screen(
                    FilterInputScreen("Duración máxima (horas)", "Ej: 20"),
                    lambda val: self.apply_filter("duration", val) if val is not None else None
                )

        self.push_screen(FilteringScreen(), handle_filter_type)

    def apply_filter(self, filter_type: str | None, value: str | None = None) -> None:
        if filter_type is None:
            self.current_library = self.full_library
            self.notify("Filtros limpiados")
        elif filter_type == "name" and value:
            f = NameFilter(value)
            filtered_games = [g for g in self.current_library.games if f.matches(g)]
            self.current_library = Library.from_iterable(filtered_games)
            self.notify(f"Filtro añadido: {value}")
        elif filter_type == "duration" and value:
            try:
                hours = float(value)
                f = DurationFilter(hours)
                filtered_games = [g for g in self.current_library.games if f.matches(g)]
                self.current_library = Library.from_iterable(filtered_games)
                self.notify(f"Filtro añadido: duración máx {hours}h")
            except ValueError:
                self.notify("Error: La duración debe ser un número", severity="error")
                return

        game_list = self.query_one(GameList)
        game_list.populate_games(self.current_library)
        game_list.select_first()

    def action_enrich_library(self) -> None:
        def handle_enricher(enricher_type: str | None) -> None:
            if enricher_type == "hltb":
                self._start_enrichment("hltb")
        self.push_screen(EnrichersScreen(), handle_enricher)

    def _start_enrichment(self, enricher_type: str) -> None:
        self.query_one("#status-message", Label).update("Enriqueciendo biblioteca...")
        self.query_one("#status-bar").add_class("active")
        self.query_one("#status-progress", ProgressBar).progress = 0
        self.run_worker(lambda: self._enrich_worker(enricher_type), thread=True)

    def _enrich_worker(self, enricher_type: str):
        try:
            if enricher_type == "hltb":
                from puntueitor.core.resolvers.hltb_resolver import HLTBResolver
                from puntueitor.core.enrichers.hltb_enricher import HLTBEnricher
                
                resolver = HLTBResolver()
                enricher = HLTBEnricher(client=resolver)
                
                games = list(self.full_library.games)
                total = len(games)
                self.call_from_thread(self._setup_progress, total)
                
                for i, game in enumerate(games, 1):
                    # Solo enriquecer si no tiene duración
                    if game.duration_hours is not None:
                        self.call_from_thread(self._update_loading_counter, i, total, game.title)
                        continue
                        
                    self.call_from_thread(self._update_loading_counter, i, total, game.title)
                    enriched_game = enricher.enrich(game)
                    
                    if enriched_game.duration_hours is not None:
                        # Guardar inmediatamente
                        self.repo.save_game(enriched_game)
                        # Actualizar interfaz en tiempo real
                        self.call_from_thread(self._on_game_enriched, enriched_game)
                
                self.call_from_thread(self._finish_enrich)
        except Exception as e:
            self.call_from_thread(self.notify, f"Error enriqueciendo: {e}", severity="error")
            self.call_from_thread(self._hide_loading)

    def _on_game_enriched(self, game: Game) -> None:
        """Actualiza un juego en la memoria y en la tabla."""
        # 1. Actualizar en full_library
        new_games = [g if g.igdb_id != game.igdb_id else game for g in self.full_library.games]
        self.full_library = Library.from_iterable(new_games)
        
        # 2. Actualizar en current_library (si está presente)
        if self.current_library.contains_igdb_id(game.igdb_id):
            new_curr = [g if g.igdb_id != game.igdb_id else game for g in self.current_library.games]
            self.current_library = Library.from_iterable(new_curr)
            
            # 3. Actualizar la fila en la DataTable a través de GameList
            game_list = self.query_one(GameList)
            game_list.update_game(game)

    def _finish_enrich(self) -> None:
        self._hide_loading()
        self.notify("Proceso de enriquecimiento finalizado")

    def _hide_loading(self) -> None:
        self.query_one("#status-bar").remove_class("active")
        self.query_one("#status-message", Label).update("Listo")

    def _setup_progress(self, total: int) -> None:
        self.query_one("#status-progress", ProgressBar).total = total

    def _update_loading_counter(self, current: int, total: int, game_name: str) -> None:
        self.query_one("#status-message", Label).update(f"Enriqueciendo: {game_name}")
        self.query_one("#status-progress", ProgressBar).progress = current

    def apply_sorting(self, criteria: str, reverse: bool = False) -> None:
        games = list(self.current_library.games)
        
        if criteria == "title":
            games.sort(key=lambda g: g.title.lower(), reverse=reverse)
        elif criteria == "user_score":
            games.sort(key=lambda g: g.user_score or 0.0, reverse=reverse)
        elif criteria == "critic_score":
            games.sort(key=lambda g: g.critic_score or 0.0, reverse=reverse)
        elif criteria == "duration":
            # Si reverse=False (Asc), None va al final (9999.0)
            # Si reverse=True (Desc), None va al final (-1.0)
            none_val = 9999.0 if not reverse else -1.0
            games.sort(key=lambda g: g.duration_hours if g.duration_hours is not None else none_val, reverse=reverse)
        elif criteria == "mixed":
            strategy = MixedScore()
            ctx = ScoringContext()
            games.sort(key=lambda g: strategy.score(g, ctx), reverse=reverse)

        self.current_library = Library.from_iterable(games)
        game_list = self.query_one(GameList)
        game_list.populate_games(self.current_library)
        game_list.select_first()
        order_str = "Descendente" if reverse else "Ascendente"
        self.notify(f"Biblioteca ordenada por: {criteria} ({order_str})")

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

            self.full_library = library
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
