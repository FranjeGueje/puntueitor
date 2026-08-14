import os
import threading
import logging

logger = logging.getLogger(__name__)
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, LoadingIndicator, Label, ProgressBar
from textual.containers import Horizontal, Center, Middle, Vertical, Container
from textual import work

from puntueitor.tui.widgets.game_list import GameList
from puntueitor.tui.widgets.game_detail import GameDetail
from puntueitor.tui.screens.configuration import ConfigurationScreen
from puntueitor.tui.screens.quit_confirmation import QuitConfirmation
from puntueitor.tui.screens.sorting import SortingScreen
from puntueitor.tui.screens.filtering import FilteringScreen
from puntueitor.tui.screens.filter_input import FilterInputScreen
from puntueitor.tui.screens.reload_confirmation import ReloadConfirmationScreen
from puntueitor.tui.screens.scoring import ScoringScreen
from puntueitor.tui.screens.game_options import GameOptionsScreen
from puntueitor.tui.screens.unknown_menu import UnknownMenuScreen
from puntueitor.tui.screens.igdb_search_results import IGDBSearchResults
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.services.game_actions import enrich_game, forget_game
from puntueitor.core.services.library_refresh import (
    refresh_library,
    regenerate_library,
)
from puntueitor.core.services.unknown_actions import (
    SearchResult,
    Unknown,
    adopt_result,
    resolve_by_store,
    search_igdb,
)
from puntueitor.core.models import Library, Game
from puntueitor import __version__

from puntueitor.core.config import ConfigManager
from puntueitor.core import paths
from puntueitor.core.igdb.service import IGDBService
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
        ("u", "toggle_unknowns", "Desconocidos"),
        ("r", "soft_reload", "Actualizar"),
        ("R", "reload_library", "Regenerar TODO"),
        ("f1", "toggle_finished", "Terminado"),
        ("f2", "toggle_backlog", "Backlog"),
        ("f3", "toggle_favorite", "Favorito"),
        ("v", "show_cover", "Carátula"),
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
        self.title = f"Puntueitor - {__version__}"
        self.full_library = Library.from_iterable(())
        self.current_library = Library.from_iterable(())
        self.is_reloading = False
        self.is_enriching = False
        self._filter_state: dict = {}
        self._is_restoring = False
        self._library_changed = False
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
            self.call_from_thread(self._on_initial_loaded, library)
        except Exception as e:
            self.call_from_thread(self.notify, f"Error cargando librería: {e}", severity="error")

    def _save_filter_state(self) -> None:
        if self._is_restoring:
            return
        from puntueitor.core.config import write_json_atomic
        write_json_atomic(paths.tui_state_file(), self._filter_state)

    def _load_filter_state(self) -> dict:
        import json
        path = paths.tui_state_file()
        if not path.exists():
            return {}
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _restore_filter_state(self) -> None:
        state = self._load_filter_state()
        if not state:
            return
        self._is_restoring = True

        show_hidden = state.pop("show_hidden", False)
        if show_hidden:
            self.query_one(GameList).show_hidden = True

        for filter_type, value in state.items():
            self.apply_filter(filter_type, value)

        game_list = self.query_one(GameList)
        game_list.populate_games(self.current_library)
        game_list.select_first()

        self._filter_state = state | {"show_hidden": show_hidden}
        self._is_restoring = False

    def _clear_filter_state(self) -> None:
        self._filter_state = {}
        path = paths.tui_state_file()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _on_initial_loaded(self, library):
        self.full_library = library
        self.current_library = library
        games = list(library.games)
        self.call_after_refresh(self._populate_batch, games, 0, 100)

    def _populate_batch(self, games, start, batch_size):
        end = min(start + batch_size, len(games))
        game_list = self.query_one(GameList)
        for game in games[start:end]:
            game_list.add_game_to_table(game)
        if end < len(games):
            self.call_after_refresh(self._populate_batch, games, end, batch_size)
        else:
            game_list.select_first()
            self.call_after_refresh(self._restore_filter_state)

    def on_unmount(self) -> None:
        self.workers.cancel_all()

    def on_game_list_game_selected(self, message: GameList.GameSelected) -> None:
        game = message.game

        def handle_options(result: dict | None) -> None:
            if result is None:
                return
            if result.get("__delete__"):
                self._delete_game(game)
                return
            if result.get("__enrich__"):
                self._enrich_single_game(game)
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

    def _enrich_single_game(self, game: Game) -> None:
        """
        Busca datos extra para este juego, sin bloquear la interfaz.

        El qué se busca vive en `core.services.game_actions`, compartido con
        el carrusel 3D; aquí solo queda el hilo y cómo se avisa de cada uno
        de los tres desenlaces.
        """
        def worker():
            result = enrich_game(self.repo, game)
            if not result.ok:
                self.call_from_thread(
                    self.notify, f"Error enriqueciendo: {result.error}",
                    severity="error",
                )
            elif result.found:
                self.call_from_thread(self._on_single_enriched, result.game)
            else:
                self.call_from_thread(
                    self.notify, f"No se encontraron datos para {game.title}",
                    severity="warning",
                )
        self.notify(f"Enriqueciendo {game.title}...")
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_single_enriched(self, game: Game) -> None:
        new_full = [g if g.igdb_id != game.igdb_id else game for g in self.full_library.games]
        self.full_library = Library.from_iterable(new_full)
        if self.current_library.contains_igdb_id(game.igdb_id):
            new_curr = [g if g.igdb_id != game.igdb_id else game for g in self.current_library.games]
            self.current_library = Library.from_iterable(new_curr)
        self.query_one(GameList).update_game(game)
        self.query_one(GameDetail).show_game(game)
        self.notify(f"Enriquecido: {game.title}")

    def _delete_game(self, game: Game) -> None:
        igdb_id = game.igdb_id
        forget_game(self.repo, game)
        self.full_library = Library.from_iterable(
            g for g in self.full_library.games if g.igdb_id != igdb_id
        )
        self.current_library = self.full_library
        game_list = self.query_one(GameList)
        game_list.populate_games(self.current_library)
        from textual.widgets import Markdown
        self.query_one(GameDetail).query_one("#game-info", Markdown).update(
            "Selecciona un juego de la lista para ver sus detalles."
        )
        self.notify(f"Eliminado: {game.title}")

    def on_game_list_game_highlighted(self, message: GameList.GameHighlighted) -> None:
        detail = self.query_one(GameDetail)
        detail.show_game(message.game)

    def on_game_list_unknown_selected(self, message: GameList.UnknownSelected) -> None:
        unknown = message.unknown

        def handle_menu(choice: str | None) -> None:
            if choice == "search_title":
                self._search_unknown_by_title(unknown)
            elif choice == "search_store":
                self._resolve_unknown_by_store(unknown)

        self.push_screen(UnknownMenuScreen(), handle_menu)

    def _search_unknown_by_title(self, unknown: dict) -> None:
        def handle_input(text: str | None) -> None:
            if text and text.strip():
                self._do_igdb_search(text.strip(), unknown)

        self.push_screen(
            FilterInputScreen(
                "Buscar en IGDB",
                "Título del juego...",
                default=unknown["title"],
            ),
            handle_input,
        )

    def _do_igdb_search(self, query: str, unknown: dict) -> None:
        results, error = search_igdb(query)
        if error is not None:
            self.notify(f"Error en búsqueda IGDB: {error}", severity="error")
            return
        if not results:
            self.notify("Sin resultados en IGDB", severity="warning")
            return

        def handle_result(raw: dict | None) -> None:
            if raw:
                self._add_igdb_result(unknown, raw["id"], raw)

        # La pantalla de resultados sigue trabajando con los crudos de IGDB,
        # que es lo que `SearchResult` lleva dentro.
        self.push_screen(IGDBSearchResults([r.raw for r in results]), handle_result)

    def _add_igdb_result(self, unknown: dict, igdb_id: int, raw: dict) -> None:
        result = adopt_result(
            self.repo, Unknown.from_row(unknown), SearchResult.from_raw(raw),
        )
        if not result.ok:
            self.notify(f"Error añadiendo: {result.error}", severity="error")
            return
        self._finish_add_game(result.game)

    def _resolve_unknown_by_store(self, unknown: dict) -> None:
        result = resolve_by_store(self.repo, Unknown.from_row(unknown))
        if result.unsupported:
            self.notify(f"Tienda no soportada: {unknown['store']}", severity="error")
        elif result.error is not None:
            self.notify(
                f"Error resolviendo {unknown['store']}: {result.error}",
                severity="error",
            )
        elif result.game is None:
            self.notify(
                f"No se encontró en IGDB para {unknown['store']}",
                severity="warning",
            )
        else:
            self._finish_add_game(result.game)

    def _finish_add_game(self, game: Game) -> None:
        """
        El juego ya está en la base de datos (y enriquecido): solo queda
        meterlo en las listas de la pantalla.
        """
        new_games = list(self.full_library.games) + [game]
        self.full_library = Library.from_iterable(new_games)
        self.current_library = self.full_library
        self._library_changed = True
        unknowns = self.repo.unknown_cacher.get_all()
        self.query_one(GameList).populate_unknowns(unknowns)
        self.notify(f"Añadido: {game.title}")

    def action_configure(self) -> None:
        def repoblar(_result=None) -> None:
            # Las tiendas marcadas deciden qué se enseña (ver
            # `GameList.populate_games`), así que hay que repintar la lista
            # al volver: si no, el cambio no se nota hasta reiniciar.
            if not getattr(self, "_showing_unknowns", False):
                self.query_one(GameList).populate_games(self.current_library)

        self.push_screen(ConfigurationScreen(), repoblar)

    def action_toggle_hidden(self) -> None:
        game_list = self.query_one(GameList)
        game_list.show_hidden = not game_list.show_hidden
        self._filter_state["show_hidden"] = game_list.show_hidden
        self._save_filter_state()
        game_list.populate_games(self.current_library if self.current_library else self.full_library)
        self.notify(
            "Mostrando juegos ocultos" if game_list.show_hidden else "Ocultando juegos ocultos"
        )

    def _toggle_game_flag(self, flag: str) -> None:
        game_list = self.query_one(GameList)
        game = game_list.get_current_game()
        if game is None:
            return
        setattr(game, flag, not getattr(game, flag))
        self.repo.library_cacher.set_status(
            game.igdb_id,
            finished=game.finished,
            hidden=game.hidden,
            backlog=game.backlog,
            favorite=game.favorite,
        )
        game_list.update_game(game)
        self.query_one(GameDetail).show_game(game)

    def action_toggle_finished(self) -> None:
        self._toggle_game_flag("finished")

    def action_toggle_backlog(self) -> None:
        self._toggle_game_flag("backlog")

    def action_toggle_favorite(self) -> None:
        self._toggle_game_flag("favorite")

    def action_show_cover(self) -> None:
        game_list = self.query_one(GameList)
        game = game_list.get_current_game()
        if game is None or not game.cover_url:
            self.notify("Este juego no tiene carátula", severity="warning")
            return
        t = threading.Thread(target=self._download_and_show_cover, args=(game,), daemon=True)
        t.start()

    def _download_and_show_cover(self, game: Game) -> None:
        import subprocess
        import urllib.request
        from pathlib import Path
        cover_dir = paths.covers_dir()
        cover_dir.mkdir(parents=True, exist_ok=True)
        cover_path = cover_dir / f"{game.igdb_id}.jpg"
        if not cover_path.exists():
            try:
                urllib.request.urlretrieve(game.cover_url, cover_path)
            except Exception as e:
                self.call_from_thread(self.notify, f"Error descargando carátula: {e}", severity="error")
                return
        subprocess.Popen(["xdg-open", str(cover_path)])

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
            if getattr(self, '_library_changed', False):
                self.full_library = self.repo.load()
                self.current_library = self.full_library
                self._library_changed = False
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
            elif filter_type in ("finished:true", "finished:false"):
                self.apply_filter("finished", filter_type.split(":")[1])
            elif filter_type in ("favorite:true", "favorite:false"):
                self.apply_filter("favorite", filter_type.split(":")[1])
            elif filter_type in ("backlog:true", "backlog:false"):
                self.apply_filter("backlog", filter_type.split(":")[1])
            elif filter_type == "hidden:true":
                self.apply_filter("hidden", "true")

        self.push_screen(FilteringScreen(), handle_filter_type)

    def apply_filter(self, filter_type: str | None, value: str | None = None) -> None:
        game_list = self.query_one(GameList)
        if filter_type is None:
            self.current_library = self.library_service.clear_filters(self.full_library)
            game_list.show_hidden = False
            self._clear_filter_state()
            self.notify("Filtros limpiados")
        elif filter_type == "name" and value:
            self.current_library = self.library_service.filter_by_name(
                self.current_library, value
            )
            self._filter_state["name"] = value
            self._save_filter_state()
            self.notify(f"Filtro añadido: {value}")
        elif filter_type == "duration" and value:
            try:
                hours = float(value)
                self.current_library = self.library_service.filter_by_duration(
                    self.current_library, hours
                )
                self._filter_state["duration"] = value
                self._save_filter_state()
                self.notify(f"Filtro añadido: duración máx {hours}h")
            except ValueError:
                self.notify("Error: La duración debe ser un número", severity="error")
                return
        elif filter_type == "finished":
            flag = value == "true"
            self.current_library = self.library_service.filter_by_finished(
                self.current_library, flag
            )
            self._filter_state["finished"] = value
            self._save_filter_state()
            self.notify(f"Filtro: {'terminados' if flag else 'no terminados'}")
        elif filter_type == "favorite":
            flag = value == "true"
            self.current_library = self.library_service.filter_by_favorite(
                self.current_library, flag
            )
            self._filter_state["favorite"] = value
            self._save_filter_state()
            self.notify(f"Filtro: {'favoritos' if flag else 'no favoritos'}")
        elif filter_type == "backlog":
            flag = value == "true"
            self.current_library = self.library_service.filter_by_backlog(
                self.current_library, flag
            )
            self._filter_state["backlog"] = value
            self._save_filter_state()
            self.notify(f"Filtro: {'backlog' if flag else 'no backlog'}")
        elif filter_type == "hidden":
            flag = value == "true"
            self.current_library = self.library_service.filter_by_hidden(
                self.current_library, flag
            )
            if flag:
                game_list.show_hidden = True
            self._filter_state["hidden"] = value
            self._filter_state["show_hidden"] = flag
            self._save_filter_state()
            self.notify(f"Filtro: ocultos")

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
        if getattr(self, '_showing_unknowns', False):
            self.notify("No disponible en modo desconocidos", severity="warning")
            return
        if self.is_reloading:
            self.notify("No se puede regenerar mientras se recarga la biblioteca", severity="warning")
            return
        if self.is_enriching:
            self.notify("Ya hay un proceso de enriquecimiento en curso", severity="warning")
            return

        self.repo.extras_cacher.clear_all()
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
            from puntueitor.core.enrichers.steam_score_enricher import SteamScoreEnricher

            hltb_resolver = HLTBResolver()
            hltb = HLTBEnricher(
                client=hltb_resolver,
                extras_cacher=self.repo.extras_cacher,
            )
            steam = SteamScoreEnricher(igdb_cacher=self.repo.igdb_cacher)

            games = list(self.full_library.games)
            total = len(games)
            self._call_from_thread_safe(self._setup_progress, total)

            for i, game in enumerate(games, 1):
                if not self.is_enriching:
                    break
                self._call_from_thread_safe(self._update_loading_counter, i, total, game.title)
                if game.duration_hours is not None and game.steam_review is not None and game.steamdb_score is not None:
                    continue
                enriched_game = steam.enrich(hltb.enrich(game))

                if enriched_game.duration_hours is not None or enriched_game.steam_review is not None or enriched_game.steamdb_score is not None:
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
        if game.duration_hours is not None or game.steam_review is not None or game.steamdb_score is not None:
            self.repo.save_game(game)

        # 2. Actualizar en full_library
        new_games = [g if g.igdb_id != game.igdb_id else game for g in self.full_library.games]
        self.full_library = Library.from_iterable(new_games)

        # 3. Actualizar en current_library (si está presente)
        if self.current_library.contains_igdb_id(game.igdb_id):
            new_curr = [g if g.igdb_id != game.igdb_id else game for g in self.current_library.games]
            self.current_library = Library.from_iterable(new_curr)

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
            self._clear_filter_state()
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

        def on_loaded(game: Game) -> None:
            self.call_from_thread(self._on_game_loaded, game)

        try:
            # Dos funciones con nombre y no una con banderas: la de regenerar
            # borra la base de datos entera, y eso tiene que leerse aquí.
            if refresh:
                regenerate_library(
                    self.repo,
                    on_game=on_loaded,
                    on_progress=progress,
                    on_enriched=on_enriched,
                )
            else:
                refresh_library(
                    self.repo,
                    force_store_refresh=force_store_refresh,
                    on_game=on_loaded,
                    on_progress=progress,
                    on_enriched=on_enriched,
                )
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
    # Lo PRIMERO, y en particular ANTES de configurar el logging: éste crea
    # el fichero de log en la ruta nueva (`filemode="w"`), y entonces la
    # migración lo vería ocupado y dejaría el log antiguo sin traer. Lo
    # mismo valdría para cualquier base de datos. Ver
    # `paths.migrate_legacy_paths`.
    paths.migrate_legacy_paths()

    log_path = paths.log_file()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        filename=str(log_path),
        filemode="w",
    )
    app = PuntueitorApp()
    app.run()
