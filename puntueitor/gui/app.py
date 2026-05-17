import os
import threading
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, LoadingIndicator, Label, ProgressBar, DataTable
from textual.containers import Horizontal, Center, Middle, Vertical, Container
from textual import work

from puntueitor.gui.widgets.game_list import GameList
from puntueitor.gui.widgets.game_detail import GameDetail
from puntueitor.gui.screens.configuration import ConfigurationScreen
from puntueitor.gui.screens.quit_confirmation import QuitConfirmation
from puntueitor.gui.screens.sorting import SortingScreen
from puntueitor.gui.screens.filtering import FilteringScreen
from puntueitor.gui.screens.filter_input import FilterInputScreen
from puntueitor.gui.screens.reload_confirmation import ReloadConfirmationScreen
from puntueitor.gui.screens.scoring import ScoringScreen
from puntueitor.gui.screens.game_options import GameOptionsScreen
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.models import Library, Game

from puntueitor.core.config import ConfigManager
from puntueitor.core.igdb.service import IGDBService
from puntueitor.core.pipeline.load_steam_library import load_steam_library
from puntueitor.core.services.library_service import LibraryService

class PuntueitorApp(App):
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("p", "select_scoring", "Puntueitor"),
        ("c", "configure", "Configurar"),
        ("o", "toggle_hidden", "Ocultos"),
        ("s", "sort_library", "Ordenar"),
        ("f", "filter_library", "Filtrar"),
        ("e", "enrich_library", "Enriquecedores"),
        ("E", "regenerate_enrichers", "Regenerar enriquecedores"),
        ("r", "soft_reload", "Actualizar"),
        ("R", "reload_library", "Regenerar TODO"),
        ("q", "request_quit", "Salir"),
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
        self.is_reloading = False
        self.is_enriching = False
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
            self.library_service = LibraryService(self.repo)
            self.run_worker(self._initial_load_worker, thread=True)
        except Exception as e:
            game_list.populate_games(Library.from_iterable(()))
            self.notify(f"Error cargando librería: {e}", severity="error")

    def _initial_load_worker(self):
        try:
            library = self.repo.load()
            self.call_from_thread(self.notify, f"repo.load() = {len(library)} games in worker")
            self.call_from_thread(self._on_initial_loaded, library)
        except Exception as e:
            self.call_from_thread(self.notify, f"Error cargando librería: {e}", severity="error")

    def _on_initial_loaded(self, library):
        self.full_library = library
        self.current_library = library
        games = list(library.games)
        self.notify(f"Library: {len(games)} games")
        self.call_after_refresh(self._populate_batch, games, 0, 100)

    def _populate_batch(self, games, start, batch_size):
        end = min(start + batch_size, len(games))
        game_list = self.query_one(GameList)
        for game in games[start:end]:
            game_list.add_game_to_table(game)
        if end < len(games):
            self.call_after_refresh(self._populate_batch, games, end, batch_size)
        else:
            rows = game_list.query_one("#game-options", DataTable).row_count
            self.notify(f"Done: Table rows={rows}, Library={len(games)}")
            game_list.select_first()

    def on_unmount(self) -> None:
        self.workers.cancel_all()

    def on_game_list_game_selected(self, message: GameList.GameSelected) -> None:
        game = message.game

        def handle_options(result: dict | None) -> None:
            if result is None:
                return
            game.finished = result["finished"]
            game.hidden = result["hidden"]
            game.backlog = result["backlog"]
            game.favorite = result["favorite"]
            self.repo.library_cacher.set_status(game.igdb_id, **result)
            game_list = self.query_one(GameList)
            game_list.populate_games(self.current_library if self.current_library else self.full_library)
            self.query_one(GameDetail).show_game(game)
            self.notify("Estado actualizado")

        self.push_screen(GameOptionsScreen(game), handle_options)

    def on_game_list_game_highlighted(self, message: GameList.GameHighlighted) -> None:
        detail = self.query_one(GameDetail)
        detail.show_game(message.game)
    
    def action_configure(self) -> None:
        self.push_screen(ConfigurationScreen())

    def action_toggle_hidden(self) -> None:
        game_list = self.query_one(GameList)
        game_list.show_hidden = not game_list.show_hidden
        game_list.populate_games(self.current_library if self.current_library else self.full_library)
        self.notify(
            "Mostrando juegos ocultos" if game_list.show_hidden else "Ocultando juegos ocultos"
        )

    def check_action(self, action: str, namespace: str) -> bool | None:
        if getattr(self, '_showing_unknowns', False):
            restricted = {
                "sort_library", "filter_library", "enrich_library",
                "regenerate_enrichers", "soft_reload", "reload_library",
                "toggle_hidden",
            }
            if action in restricted:
                return False
        return True

    def action_toggle_unknowns(self) -> None:
        game_list = self.query_one(GameList)
        if not getattr(self, '_showing_unknowns', False):
            self._saved_library = self.current_library
            unknowns = self.repo.unknown_cacher.get_all()
            game_list.populate_unknowns(unknowns)
            self._showing_unknowns = True
            self.notify(f"Mostrando {len(unknowns)} desconocidos")
        else:
            self.current_library = self._saved_library
            game_list.populate_games(self.current_library)
            self._showing_unknowns = False
            self.notify("Volviendo a biblioteca")
        self._refresh_footer()

    def _refresh_footer(self) -> None:
        self.screen.refresh_bindings()

    def action_request_quit(self) -> None:
        def check_quit(should_quit: bool) -> None:
            if should_quit:
                self.is_enriching = False
                self.is_reloading = False
                self.workers.cancel_all()
                self.exit()
        
        self.push_screen(QuitConfirmation(), check_quit)

    def action_sort_library(self) -> None:
        if getattr(self, '_showing_unknowns', False):
            self.notify("No disponible en modo desconocidos", severity="warning")
            return
        def handle_sorting(result: tuple[str, bool] | None) -> None:
            if result:
                criteria, reverse = result
                self.apply_sorting(criteria, reverse)
        
        self.push_screen(SortingScreen(), handle_sorting)

    def action_filter_library(self) -> None:
        if getattr(self, '_showing_unknowns', False):
            self.notify("No disponible en modo desconocidos", severity="warning")
            return
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
            elif filter_type in ("finished", "not_finished", "backlog", "not_backlog",
                                "favorite", "not_favorite", "hidden", "not_hidden"):
                self.apply_filter(filter_type)

        self.push_screen(FilteringScreen(), handle_filter_type)

    def apply_filter(self, filter_type: str | None, value: str | None = None) -> None:
        if filter_type is None:
            self.current_library = self.library_service.clear_filters(self.full_library)
            self.notify("Filtros limpiados")
        elif filter_type == "name" and value:
            self.current_library = self.library_service.filter_by_name(
                self.current_library, value
            )
            self.notify(f"Filtro añadido: {value}")
        elif filter_type == "duration" and value:
            try:
                hours = float(value)
                self.current_library = self.library_service.filter_by_duration(
                    self.current_library, hours
                )
                self.notify(f"Filtro añadido: duración máx {hours}h")
            except ValueError:
                self.notify("Error: La duración debe ser un número", severity="error")
                return

        elif filter_type == "finished":
            self.current_library = self.library_service.filter_by_finished(self.current_library)
            self.notify("Filtro: solo terminados")
        elif filter_type == "not_finished":
            self.current_library = self.library_service.filter_by_not_finished(self.current_library)
            self.notify("Filtro: no terminados")
        elif filter_type == "backlog":
            self.current_library = self.library_service.filter_by_backlog(self.current_library)
            self.notify("Filtro: solo backlog")
        elif filter_type == "not_backlog":
            self.current_library = self.library_service.filter_by_not_backlog(self.current_library)
            self.notify("Filtro: no backlog")
        elif filter_type == "favorite":
            self.current_library = self.library_service.filter_by_favorite(self.current_library)
            self.notify("Filtro: solo favoritos")
        elif filter_type == "not_favorite":
            self.current_library = self.library_service.filter_by_not_favorite(self.current_library)
            self.notify("Filtro: no favoritos")
        elif filter_type == "hidden":
            self.current_library = self.library_service.filter_by_hidden(self.current_library)
            self.notify("Filtro: solo ocultos")
        elif filter_type == "not_hidden":
            self.current_library = self.library_service.filter_by_not_hidden(self.current_library)
            self.notify("Filtro: no ocultos")

        game_list = self.query_one(GameList)
        game_list.populate_games(self.current_library)
        game_list.select_first()

    def action_enrich_library(self) -> None:
        if getattr(self, '_showing_unknowns', False):
            self.notify("No disponible en modo desconocidos", severity="warning")
            return
        if self.is_reloading:
            self.notify("No se puede enriquecer mientras se recarga la biblioteca", severity="warning")
            return
        if self.is_enriching:
            self.notify("Ya hay un proceso de enriquecimiento en curso", severity="warning")
            return
        
        self._start_enrichment()

    def _call_from_thread_safe(self, method, *args):
        try:
            self.call_from_thread(method, *args)
        except RuntimeError:
            pass

    def action_regenerate_enrichers(self) -> None:
        if self.is_reloading:
            self.notify("No se puede regenerar mientras se recarga la biblioteca", severity="warning")
            return
        if self.is_enriching:
            self.notify("Ya hay un proceso de enriquecimiento en curso", severity="warning")
            return

        extras_path = Path.home() / ".cache" / "puntueitor" / "extras.sqlite"
        if extras_path.exists():
            extras_path.unlink()
        self.notify("Caché de enriquecedores borrada. Recargando biblioteca...")

        library = self.repo.load()
        self.full_library = library
        self.current_library = library
        self.query_one(GameList).populate_games(library)
        self.query_one(GameList).select_first()

        self._start_enrichment()

    def action_select_scoring(self) -> None:
        def handle_scoring(scoring_type: str | None) -> None:
            if scoring_type:
                self.apply_scoring(scoring_type)
        self.push_screen(ScoringScreen(), handle_scoring)

    def apply_scoring(self, scoring_type: str) -> None:
        self.current_library, scores_map = self.library_service.score(
            self.current_library, scoring_type
        )

        game_list = self.query_one(GameList)
        game_list.populate_games(self.current_library, scores=scores_map)
        game_list.select_first()
        self.notify(f"Biblioteca puntuada y ordenada por: {scoring_type}")

    def _start_enrichment(self) -> None:
        self.is_enriching = True
        self.query_one("#status-message", Label).update("Enriqueciendo biblioteca...")
        self.query_one("#status-bar").add_class("active")
        self.query_one("#status-progress", ProgressBar).progress = 0
        t = threading.Thread(target=self._enrich_worker, daemon=True)
        t.start()

    def _enrich_worker(self):
        try:
            from puntueitor.core.resolvers.hltb_resolver import HLTBResolver
            from puntueitor.core.enrichers.hltb_enricher import HLTBEnricher
            
            resolver = HLTBResolver()
            enricher = HLTBEnricher(client=resolver)
            
            games = list(self.full_library.games)
            total = len(games)
            self._call_from_thread_safe(self._setup_progress, total)

            for i, game in enumerate(games, 1):
                if not self.is_enriching:
                    break
                self._call_from_thread_safe(self._update_loading_counter, i, total, game.title)
                if game.duration_hours is not None:
                    continue
                enriched_game = enricher.enrich(game)

                if enriched_game.duration_hours is not None:
                    self.repo.save_game(enriched_game)
                    self._call_from_thread_safe(self._on_game_enriched, enriched_game)

            self._call_from_thread_safe(self._finish_enrich)
        except Exception as e:
            self.is_enriching = False
            self._call_from_thread_safe(self.notify, f"Error enriqueciendo: {e}", severity="error")
            self._call_from_thread_safe(self._hide_loading)

    def _on_game_enriched(self, game: Game) -> None:
        """Actualiza un juego en la memoria y en la tabla."""
        # 1. Guardar los extras del juego enriquecido en el repositorio (guardado progresivo)
        if game.duration_hours is not None:
            self.repo.save_game(game)

        # 2. Actualizar en full_library
        # 1. Guardar los extras del juego enriquecido en el repositorio (guardado progresivo)
        if game.duration_hours is not None:
            self.repo.save_game(game)

        # 2. Actualizar en full_library
        new_games = [g if g.igdb_id != game.igdb_id else game for g in self.full_library.games]
        self.full_library = Library.from_iterable(new_games)

        # 3. Actualizar en current_library (si está presente)

        # 3. Actualizar en current_library (si está presente)
        if self.current_library.contains_igdb_id(game.igdb_id):
            new_curr = [g if g.igdb_id != game.igdb_id else game for g in self.current_library.games]
            self.current_library = Library.from_iterable(new_curr)

            # 4. Actualizar la fila en la DataTable a través de GameList

            # 4. Actualizar la fila en la DataTable a través de GameList
            game_list = self.query_one(GameList)
            game_list.update_game(game)

    def _finish_enrich(self) -> None:
        self.is_enriching = False
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
        self.current_library = self.library_service.sort(
            self.current_library, criteria, reverse
        )
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


    def action_soft_reload(self) -> None:
        """r: actualiza tiendas desde API y añade solo juegos nuevos a resolvers/igdb."""
        if getattr(self, '_showing_unknowns', False):
            self.notify("No disponible en modo desconocidos", severity="warning")
            return
        if self.is_reloading:
            self.notify("Ya hay una recarga en curso", severity="warning")
            return
        if self.is_enriching:
            self.notify("No se puede recargar mientras se enriquece la biblioteca", severity="warning")
            return
        if not self._check_config():
            return
        self._start_reload(refresh=False)

    def action_reload_library(self) -> None:
        """R: borra toda la caché SQLite y recarga todo desde cero."""
        if getattr(self, '_showing_unknowns', False):
            self.notify("No disponible en modo desconocidos", severity="warning")
            return
        if self.is_reloading:
            self.notify("Ya hay una recarga en curso", severity="warning")
            return
        if self.is_enriching:
            self.notify("No se puede recargar mientras se enriquece la biblioteca", severity="warning")
            return
        if not self._check_config():
            return
            
        def handle_confirmation(confirmed: bool) -> None:
            if confirmed:
                self._start_reload(refresh=True)
                
        self.push_screen(ReloadConfirmationScreen(), handle_confirmation)

    def _start_reload(self, refresh: bool) -> None:
        self.is_reloading = True
        self.query_one("#status-message", Label).update("Iniciando recarga...")
        self.query_one("#status-bar").add_class("active")
        self.query_one("#status-progress", ProgressBar).progress = 0
        
        if refresh:
            self.full_library = Library.from_iterable(())
            self.current_library = self.full_library
            self.query_one(GameList).populate_games(self.current_library)

        self.run_worker(lambda: self.do_reload(refresh=refresh, force_store_refresh=True), thread=True)

    @work(thread=True)
    def do_reload(self, refresh: bool = False, force_store_refresh: bool = False) -> None:
        def progress(current: int, total: int, name: str) -> None:
            self.call_from_thread(self._update_reload_progress, current, total, name)

        def on_enriched(enriched_game: Game) -> None:
            self.call_from_thread(self._on_game_enriched, enriched_game)

        try:
            if refresh:
                cache_dir = Path.home() / ".cache" / "puntueitor"
                for db_file in cache_dir.glob("*.sqlite"):
                    try: os.remove(db_file)
                    except: pass

            from puntueitor.core.igdb.service import IGDBService
            from puntueitor.core.pipeline.load_steam_library import load_library
            from puntueitor.core.pipeline.load_steam_library import load_library
            from puntueitor.core.resolvers.hltb_resolver import HLTBResolver
            from puntueitor.core.enrichers.hltb_enricher import HLTBEnricher
            from puntueitor.core.heroics import HeroicsLoader
            from puntueitor.core.config import ConfigManager

            config = ConfigManager().get
            igdb_service = IGDBService()

            heroic_loader = None
            if getattr(config, 'heroic_is_active', False):
                heroic_loader = HeroicsLoader()

            extras_cache = self.repo.extras_cacher.get_all_extras()

            enrichers = []
            try:
                hltb_resolver = HLTBResolver()
                hltb_enricher = HLTBEnricher(client=hltb_resolver, overwrite=False)
                enrichers.append(hltb_enricher)
            except Exception as e:
                self.call_from_thread(self.notify, f"Warning: No se pudo inicializar HLTB: {e}", severity="warning")

            game_generator = load_library(
                engine=igdb_service,
                heroic_loader=heroic_loader,
                heroic_loader=heroic_loader,
                refresh=refresh,
                force_store_refresh=force_store_refresh,
                progress_callback=progress,
                enrichers=enrichers if enrichers else None,
                enrichment_callback=on_enriched if enrichers else None,
                extras_cache=extras_cache if extras_cache else None,
                extras_cache=extras_cache if extras_cache else None,
            )

            loaded_games = []
            executor = None

            for item in game_generator:
                # El último item puede ser el executor (ThreadPoolExecutor o None)
                if hasattr(item, 'duration_hours'):
                    # Es un juego
                    loaded_games.append(item)
                    # Guardado progresivo: guardar juego inmediatamente si tiene duration
                    if item.duration_hours is not None:
                        self.repo.save_game(item)
                    self.call_from_thread(self._on_game_loaded, item)
                else:
                    # Es el executor
                    executor = item

            # Cerrar el executor inmediatamente (sin esperar a que terminen los enrichers)
            if executor:
                try:
                    executor.shutdown(wait=False)
                except Exception as e:
                    logger.warning(f"Error shutting down executor: {e}")

            new_library = Library.from_iterable(loaded_games)
            logger.info("do_reload: saving library...")
            self.repo.save(new_library)
            logger.info("do_reload: finished successfully")
            self.call_from_thread(self._finish_reload, refresh)

        except Exception as e:
            logger.exception("do_reload FAILED")
            self.is_reloading = False
            self.call_from_thread(self._handle_reload_error, str(e))

    def _on_game_loaded(self, game: Game) -> None:
        if self.full_library.contains_igdb_id(game.igdb_id):
            return
        new_games = list(self.full_library.games)
        new_games.append(game)
        self.full_library = Library.from_iterable(new_games)
        self.current_library = self.full_library
        self.query_one(GameList).add_game_to_table(game)
        
        if game.duration_hours is not None:
            self.repo.save_game(game)

    def _finish_reload(self, refresh: bool = False) -> None:
        self.is_reloading = False
        self._hide_loading()
        msg = "¡Biblioteca recargada!" if refresh else "¡Actualización finalizada!"
        self.notify(msg)
        self.query_one(GameList).select_first()

    def _handle_reload_error(self, error_msg: str) -> None:
        self._hide_loading()
        self.notify(f"Fallo al recargar: {error_msg}", severity="error")

    def _update_reload_progress(self, current: int, total: int, name: str) -> None:
        self.query_one("#status-message", Label).update(f"Cargando IGDB: {name}")
        bar = self.query_one("#status-progress", ProgressBar)
        bar.total = total
        bar.progress = current

if __name__ == "__main__":
    LOG_DIR = Path.home() / ".cache" / "puntueitor"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        filename=str(LOG_DIR / "puntueitor.log"),
        filemode="w",
    )
    app = PuntueitorApp()
    app.run()
