"""
Las tres pantallas de Opciones que configuran algo: Cuentas, Tiendas y los
ajustes propios del carrusel (Puntueitor3D).

Tercer trozo que sale de `gui3d/app.py`. Van en el mismo módulo porque
comparten la misma mecánica —una copia en edición y "Guardar" que la aplica—,
a diferencia de Avanzado o Créditos, que no editan nada.

`open_config_form` es compartida de verdad por Cuentas y Tiendas: son dos
ventanas sobre los mismos `app._settings`, y una copia por menú haría que
guardar en uno pisara lo editado en el otro.
"""
import dataclasses
import logging

from puntueitor.core.config import ConfigManager
from puntueitor.gui3d import menus, state

logger = logging.getLogger(__name__)


def persist_filters(app) -> None:
    """
    Guarda los filtros, si el usuario quiere que se recuerden.

    Con "Cargar filtros al inicio" en No NO se borra lo que ya hubiera
    guardado, solo se deja de escribir: así, al volver a activarlo, se
    recuperan los de la última vez en lugar de empezar de cero.
    """
    if app.prefs.remember_filters:
        state.save_filters(app.filters)


def open_gui3d_menu(app) -> None:
    """
    "Puntueitor3D" dentro de Opciones: los ajustes propios del carrusel.

    Se edita sobre una COPIA y solo se aplica al dar a "Guardar", igual
    que los menús de Cuentas y Tiendas y los formularios de scoring. Así salir
    con B descarta, que es lo que espera quien ya conoce el resto de
    menús — antes estos dos ajustes se aplicaban al instante y eran la
    excepción.
    """
    app._gui3d_prefs = dataclasses.replace(app.prefs)
    app.gui3d_menu.set_items(menus.build_gui3d_items(app._gui3d_prefs))
    app._push_menu(app.gui3d_menu)


def adjust_gui3d_setting(app, item, direction: int) -> None:
    """Rota el ajuste enfocado, SOLO en la copia en edición."""
    if item.key == "set3d:score_source":
        fuentes = state.SCORE_SOURCES
        actual = fuentes.index(app._gui3d_prefs.score_source)
        app._gui3d_prefs.score_source = fuentes[
            (actual + direction) % len(fuentes)
        ]
    elif item.key == "set3d:remember_filters":
        app._gui3d_prefs.remember_filters = (
            not app._gui3d_prefs.remember_filters
        )
    else:
        return

    refresh_gui3d_menu(app)


def save_gui3d_settings(app) -> None:
    """
    Aplica los ajustes editados: los guarda y repinta las cajas.

    El repintado va aquí y no al cambiar el valor porque hasta ahora no
    había nada que aplicar: la copia era solo intención. `set_score_source`
    no hace nada si la nota no ha cambiado, así que guardar sin haber
    tocado esa opción no cuesta recorrer las cajas.
    """
    app.prefs = app._gui3d_prefs
    state.save_preferences(app.prefs)
    app.carousel.set_score_source(
        app.prefs.score_source, app._labels_visible,
    )
    app.notifier.show("Configuración guardada")
    logger.info(f"gui3d: ajustes guardados: {app.prefs}")
    app._pop_menu()


def refresh_gui3d_menu(app) -> None:
    """Repinta los valores sin rehacer el menú, para no perder el foco."""
    nuevos = {
        item.key: item for item in menus.build_gui3d_items(app._gui3d_prefs)
    }
    for item in app.gui3d_menu.items:
        nuevo = nuevos.get(item.key)
        if nuevo is not None:
            item.value = nuevo.value
    app.gui3d_menu.refresh_values()



def open_accounts_menu(app) -> None:
    """"Cuentas": credenciales de IGDB y Steam, y sesiones de tienda."""
    open_config_form(app, app.accounts_menu, menus.build_accounts_items)


def open_settings_menu(app) -> None:
    """"Tiendas": qué tiendas se cargan."""
    open_config_form(app, app.settings_menu, menus.build_settings_items)


def open_config_form(app, menu, builder) -> None:
    """
    Abre uno de los dos formularios sobre la configuración.

    Los dos comparten `app._settings` y `_save_settings`: son ventanas
    distintas a los mismos ajustes, y tener una copia por menú haría que
    guardar en uno pisara lo editado en el otro.

    Se edita sobre una COPIA de los valores guardados y solo se escribe
    al dar a "Guardar", así que salir con B deja la configuración como
    estaba. Importa más aquí que en otros formularios: lo que hay dentro
    son las credenciales, y perderlas por un roce en un botón sería
    bastante peor que perder un peso de scoring.
    """
    config = ConfigManager().get
    app._settings = {
        field: getattr(config, field)
        for field, _, _ in menus.SETTINGS_TEXTS
    }
    app._settings.update({
        field: getattr(config, field) for field, _ in menus.SETTINGS_STORES
    })
    app._sessions = read_sessions()
    # Se recuerda con qué se pintó para poder repintarlo igual sin tener
    # que preguntar cuál de los dos menús está delante.
    app._settings_builder = builder

    menu.set_items(builder(app._settings, app._sessions))
    app._push_menu(menu)


def refresh_settings_menu(app) -> None:
    """Repinta los valores sin rehacer el menú, para no perder el foco."""
    builder = getattr(app, "_settings_builder", menus.build_settings_items)
    menu = (
        app.accounts_menu
        if builder is menus.build_accounts_items
        else app.settings_menu
    )
    nuevos = {
        item.key: item
        for item in builder(app._settings, app._sessions)
    }
    for item in menu.items:
        nuevo = nuevos.get(item.key)
        if nuevo is not None:
            item.value = nuevo.value
    menu.refresh_values()


def read_sessions() -> dict:
    """En qué tiendas hay sesión, para pintarlo al lado de cada una."""
    from puntueitor.core.services import accounts

    return accounts.sessions_summary()


def activate_setting(app, key: str) -> None:
    if key == "set:save":
        save_settings(app)
        return

    if key.startswith("login:"):
        start_login(app, key.removeprefix("login:"))
        return

    field = key.removeprefix("set:")
    label = next(
        (etiqueta for campo, etiqueta, _ in menus.SETTINGS_TEXTS if campo == field),
        field,
    )
    app._open_text_prompt(
        title=label,
        initial=str(app._settings.get(field) or ""),
        on_accept=lambda text: set_setting(app, field, text),
    )


def start_login(app, store: str) -> None:
    """
    Abre el navegador y deja el teclado esperando lo que hay que pegar.

    Encadenado a propósito: si el aviso y el campo fueran dos pasos, el
    usuario volvería del navegador con el portapapeles cargado a un menú
    que ya no está esperando nada.
    """
    from puntueitor.core.services import accounts

    resultado = accounts.open_login(store)
    app.notifier.show(resultado.mensaje)
    if not resultado.ok:
        return

    app._open_text_prompt(
        title=f"Pega aquí lo que te ha dado {store.upper()}",
        initial="",
        on_accept=lambda texto: finish_login(app, store, texto),
    )


def finish_login(app, store: str, texto: str) -> None:
    from puntueitor.core.services import accounts

    resultado = accounts.finish_login(store, texto)
    app.notifier.show(resultado.mensaje)
    app._sessions = read_sessions()
    refresh_settings_menu(app)


def set_setting(app, field: str, text: str) -> None:
    if field == "steam_user_id":
        # Numérico; lo que no se entienda se queda en 0, igual que la
        # TUI, en vez de dejar la configuración a medio escribir.
        app._settings[field] = int(text) if text.isdigit() else 0
    else:
        app._settings[field] = text
    refresh_settings_menu(app)


def toggle_setting_store(app, item) -> None:
    field = item.payload.get("field")
    if field is not None:
        app._settings[field] = item.checked


def save_settings(app) -> None:
    manager = ConfigManager()
    config = manager.get
    for field, value in app._settings.items():
        setattr(config, field, value)
    manager.save()

    # Las tiendas marcadas deciden qué se ve (ver `_visible_entries`),
    # así que el cambio tiene que notarse ya, sin reiniciar.
    app._apply_order()
    app._on_selection_changed()

    app.notifier.show("Configuración guardada")
    logger.info("gui3d: configuración de la aplicación guardada")
    app._pop_menu()
