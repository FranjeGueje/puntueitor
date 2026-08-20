"""
Elegir un sistema de puntuación y configurar sus pesos, horas o géneros.

Segundo trozo que sale de `gui3d/app.py`. Las funciones reciben la
aplicación como argumento explícito, no un mixin: lo que necesitan de ella
—el menú de scoring, `library_repository`, el notificador, los campos de
edición en curso— se ve en la firma.

Dos cosas se quedan en `App` a propósito, aunque estaban en el mismo bloque
marcado "Scoring" en el fichero original:

- `_on_game_flag_toggled` no es de scoring, es del menú de juego (las
  casillas de terminado/oculto/favorito). Le tocará su propio trozo.
- `_ask_confirm` / `_run_confirmed_action` son el diálogo de sí/no genérico.
  Ya lo usa `backup_ui.py`; moverlo aquí forzaría que ese módulo importara
  este, que es justo el acoplamiento que se está quitando.
"""
import logging

from puntueitor.core.config import DEFAULT_AVAILABLE_HOURS
from puntueitor.core.models import Library
from puntueitor.core.services.library_service import LibraryService
from puntueitor.gui3d import scoring_config, scoring_info, sorting
from puntueitor.gui3d.menu import MenuItem

logger = logging.getLogger(__name__)



def refresh_scoring_description(app) -> None:
    """
    Pone en la franja de abajo la descripción del sistema enfocado.

    Se llama tras cada movimiento del foco (ver `_navigate`), que es lo
    que hace que la descripción vaya cambiando al recorrer la lista, como
    en la TUI.
    """
    item = app.scoring_menu.focused_item
    scorer = scoring_info.BY_KEY.get(item.key) if item else None
    if scorer is None:
        return
    app.scoring_title_text.setText(scorer.title)
    app.scoring_desc_text.setText(scoring_info.description_for(scorer.key))


def show_scoring_description(app, visible: bool) -> None:
    if visible:
        refresh_scoring_description(app)
        app.scoring_frame.show()
    else:
        app.scoring_frame.hide()


def apply_scorer(app, scoring_key: str) -> None:
    """
    A sobre un sistema: puntúa la biblioteca y ordena el carrusel por esa
    nota.

    Se delega en `LibraryService.score`, el mismo camino que usa la TUI,
    para que las dos interfaces den exactamente el mismo ranking con la
    misma configuración. De ahí sale una nota por juego, y con ella se
    arma un criterio de ordenación al vuelo (`sorting.scorer_criterion`).
    """
    scorer = scoring_info.BY_KEY.get(scoring_key)
    if scorer is None:
        return

    library = Library.from_iterable(
        entry.game for entry in app.entries if entry.game is not None
    )
    _scored, scores = LibraryService(app.library_repository).score(
        library, scoring_key,
    )
    if not scores:
        app.notifier.show("Ese sistema no ha podido puntuar")
        logger.warning(f"gui3d: {scoring_key!r} no devolvió puntuaciones")
        return

    app._sort_criterion = sorting.scorer_criterion(scorer.name, scores)
    app._close_all_menus()
    app._apply_order(reset_selection=True)
    app._on_selection_changed()
    app.notifier.show(f"Puntuado: {scorer.name}")
    logger.info(f"gui3d: biblioteca puntuada con {scoring_key!r}")


def configure_focused_scoring(app) -> None:
    """X sobre un sistema: abre su formulario de configuración."""
    item = app.scoring_menu.focused_item
    scorer = scoring_info.BY_KEY.get(item.key) if item else None
    if scorer is None:
        return
    open_scoring_config(app, scorer)


def open_scoring_config(app, scorer) -> None:
    """
    Abre el formulario del sistema `scorer`, con los valores que tiene
    guardados ahora mismo.

    Los pesos se editan sobre una copia (`_config_weights`) y solo se
    escriben en la configuración al dar a "Guardar": repartir tres
    porcentajes obliga a pasar por estados que no suman 100 (bajas uno
    para subir otro), así que guardar en cada cambio sería imposible.

    Es la ÚNICA excepción que queda: Cuentas, Tiendas y Puntueitor3D guardan
    cada ajuste al tocarlo y ya no tienen fila de "Guardar" (ver
    `gui3d/accounts_ui.py`). Aquí se aplica en bloque porque lo que se edita
    es un reparto, no ajustes sueltos.
    """
    app._config_scorer = scorer
    if scorer.config_form == "weights":
        app._config_weights = scoring_config.weights_of(scorer.key)
    elif scorer.config_form == "hours":
        app._config_hours = scoring_config.available_hours()
    elif scorer.config_form == "genres":
        app._config_genres = scoring_config.preferred_genres()

    app.scoring_config_menu.set_title(f"{scorer.name}: configuración")
    app.scoring_config_menu.set_items(build_config_items(app))
    app._push_menu(app.scoring_config_menu)


def build_config_items(app) -> list:
    """Las filas del formulario, según el tipo de configuración."""
    scorer = app._config_scorer
    if scorer.config_form == "weights":
        items = [
            MenuItem(
                f"cfg:weight:{field}", label, kind="cycle",
                value=f"{app._config_weights[field]:g} %",
                payload={"weight": field},
            )
            for field, label in scoring_config.WEIGHT_FIELDS
        ]
        total = scoring_config.weights_sum(app._config_weights)
        ok = scoring_config.weights_are_valid(app._config_weights)
        # La suma se enseña siempre, como en la TUI: sin ella no hay
        # forma de saber por qué "Guardar" no hace nada.
        items.append(MenuItem(
            "cfg:sum",
            f"Suma: {total:g} %" + ("" if ok else "  (debe ser 100)"),
            kind="header",
        ))
    elif scorer.config_form == "hours":
        items = [MenuItem(
            "cfg:hours", "Horas disponibles", kind="cycle",
            value=f"{app._config_hours:g} h",
            payload={"hours": True},
        )]
    else:
        genres = scoring_config.all_genres()
        items = [
            MenuItem(
                f"cfg:genre:{genre}", genre, kind="check",
                checked=genre in app._config_genres,
                payload={"genre": genre},
            )
            for genre in genres
        ] or [MenuItem("cfg:nogenres", "No hay géneros en la caché", kind="header")]

    items.append(MenuItem("cfg:sep", "", kind="header"))
    items.append(MenuItem("cfg:save", "Guardar"))
    items.append(MenuItem("cfg:reset", "Restaurar valores por defecto"))
    return items


def refresh_config_menu(app) -> None:
    """
    Repinta los valores del formulario SIN rehacerlo.

    Con `set_items` el foco volvía al primer elemento en cada cambio, así
    que al mantener izquierda sobre "Usuarios" el primer paso lo bajaba a
    él y los siguientes ya iban a "Críticos", en silencio. Aquí se
    modifican el valor (y la etiqueta de la suma, que también cambia) de
    los elementos que ya existen y se repintan sus textos, que es lo que
    conserva el foco.
    """
    menu = app.scoring_config_menu
    nuevos = {item.key: item for item in build_config_items(app)}
    for item in menu.items:
        nuevo = nuevos.get(item.key)
        if nuevo is None:
            continue
        item.value = nuevo.value
        item.label = nuevo.label
    menu.refresh_values()


def activate_config(app, key: str) -> None:
    """Qué hace elegir (A) cada fila del formulario de configuración."""
    if key == "cfg:save":
        save_scoring_config(app)
    elif key == "cfg:reset":
        reset_scoring_config(app)
    # Los pesos y las horas no responden a A: se ajustan con izquierda y
    # derecha (ver `_adjust_config_value`).


def adjust_config_value(app, item, direction: int) -> None:
    """
    Sube o baja de uno en uno el valor de la fila enfocada.

    Antes cada valor abría un cuadro de texto; con dos flechas se cambia
    en el sitio y no hay que salir del formulario para retocar un número.

    Los pesos se limitan a 0-100 (un porcentaje fuera de ahí no
    significa nada) y las horas no bajan de 1 (cero horas disponibles
    haría que ningún juego encajara). Ni unos ni otras se guardan aquí:
    eso es cosa de "Guardar".
    """
    if "weight" in item.payload:
        field = item.payload["weight"]
        current = app._config_weights[field]
        app._config_weights[field] = min(100.0, max(0.0, current + direction))
    elif "hours" in item.payload:
        app._config_hours = max(1.0, app._config_hours + direction)
    else:
        return
    refresh_config_menu(app)


def toggle_config_genre(app, item) -> None:
    genre = item.payload.get("genre")
    if genre is None:
        return
    if item.checked:
        app._config_genres.add(genre)
    else:
        app._config_genres.discard(genre)


def save_scoring_config(app) -> None:
    scorer = app._config_scorer
    if scorer.config_form == "weights":
        if not scoring_config.save_weights(scorer.key, app._config_weights):
            app.notifier.show("Los pesos deben sumar 100")
            return
    elif scorer.config_form == "hours":
        scoring_config.save_available_hours(app._config_hours)
    elif scorer.config_form == "genres":
        scoring_config.save_preferred_genres(app._config_genres)

    app.notifier.show("Configuración guardada")
    app._pop_menu()


def reset_scoring_config(app) -> None:
    scorer = app._config_scorer
    if scorer.config_form == "weights":
        app._config_weights = scoring_config.default_weights(scorer.key)
    elif scorer.config_form == "hours":
        app._config_hours = DEFAULT_AVAILABLE_HOURS
    else:
        app._config_genres = set()
    refresh_config_menu(app)
    app.notifier.show("Valores restaurados")
