"""
Las tres pantallas de Opciones que configuran algo: Cuentas, Tiendas y los
ajustes propios del carrusel (Puntueitor3D).

Tercer trozo que sale de `gui3d/app.py`. Van en el mismo módulo porque
comparten la misma mecánica —**cada ajuste se escribe al terminar de tocarlo**,
sin fila de "Guardar"—, a diferencia de Avanzado o Créditos, que no editan
nada.

Antes se editaba sobre una copia y solo se aplicaba al elegir "Guardar", que
además cerraba el menú. Eso convertía en un viaje lo que es un gesto: escribir
el Client ID de itch.io obligaba a guardar, salir de Cuentas y volver a entrar
para poder iniciar sesión con él. Ahora el dato está en disco en cuanto se
acepta, y la fila de login de al lado ya lo encuentra.

El precio, a sabiendas: en estos tres menús B ya no descarta, solo cierra. Los
formularios de scoring (`gui3d/scoring_ui.py`) sí conservan la copia, porque
allí se edita un juego de pesos que solo tiene sentido completo.

`open_config_form` es compartida de verdad por Cuentas y Tiendas: son dos
ventanas sobre los mismos `app._settings`, y una copia por menú haría que
escribir en uno pisara lo del otro.
"""
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
    """"Puntueitor3D" dentro de Opciones: los ajustes propios del carrusel."""
    app.gui3d_menu.set_items(menus.build_gui3d_items(app.prefs))
    app._push_menu(app.gui3d_menu)


def adjust_gui3d_setting(app, item, direction: int) -> None:
    """
    Rota el ajuste enfocado, y lo guarda y aplica en el acto.

    Aplicarlo ya no es solo por uniformidad con el resto de Opciones: el
    volumen se busca a tientas, y tener que guardar para oír cómo ha quedado
    hacía imposible ajustarlo.
    """
    if item.key == "set3d:score_source":
        fuentes = state.SCORE_SOURCES
        actual = fuentes.index(app.prefs.score_source)
        app.prefs.score_source = fuentes[(actual + direction) % len(fuentes)]
    elif item.key in ("set3d:music_volume", "set3d:sfx_volume"):
        campo = item.key.removeprefix("set3d:")
        paso = menus.VOLUME_STEP * (1 if direction > 0 else -1)
        # Sin dar la vuelta: un volumen es una escala con dos extremos, y
        # que bajar del todo lo dejara a tope sería una sorpresa desagradable
        # con los cascos puestos. Los otros dos ajustes sí rotan porque son
        # listas de opciones, no una magnitud.
        actual = getattr(app.prefs, campo)
        setattr(app.prefs, campo, max(0, min(100, actual + paso)))
    elif item.key == "set3d:remember_filters":
        app.prefs.remember_filters = not app.prefs.remember_filters
    else:
        return

    apply_gui3d_settings(app)
    refresh_gui3d_menu(app)


def apply_gui3d_settings(app) -> None:
    """
    Guarda las preferencias y las lleva a donde tienen efecto.

    `set_score_source` sale por la puerta si la nota no ha cambiado, así que
    mover el volumen no cuesta recorrer todas las cajas.
    """
    state.save_preferences(app.prefs)
    app.carousel.set_score_source(app.prefs.score_source, app._labels_visible)
    app.audio.set_volumes(app.prefs.music_volume, app.prefs.sfx_volume)
    logger.info(f"gui3d: ajustes guardados: {app.prefs}")


def refresh_gui3d_menu(app) -> None:
    """Repinta los valores sin rehacer el menú, para no perder el foco."""
    nuevos = {item.key: item for item in menus.build_gui3d_items(app.prefs)}
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

    Los dos comparten `app._settings` y `persist_setting`: son ventanas
    distintas a los mismos ajustes, y tener una copia por menú haría que
    escribir en uno pisara lo del otro.

    `app._settings` es un ESPEJO de lo guardado, no un borrador: es de donde
    los constructores sacan lo que pintan, y cada cambio va al disco en el
    momento (ver `persist_setting`).
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
    """Lo escrito en un campo de texto, ya guardado al aceptar el cuadro."""
    if field == "steam_user_id":
        # Numérico; lo que no se entienda se queda en 0, igual que la
        # TUI, en vez de dejar la configuración a medio escribir.
        valor = int(text) if text.isdigit() else 0
    else:
        valor = text
    persist_setting(app, field, valor)
    refresh_settings_menu(app)


def toggle_setting_store(app, item) -> None:
    """Una tienda marcada o desmarcada, guardada y aplicada en el momento."""
    field = item.payload.get("field")
    if field is None:
        return
    persist_setting(app, field, item.checked)

    # Las tiendas marcadas deciden qué se ve (ver `_visible_entries`),
    # así que el cambio tiene que notarse ya, sin reiniciar.
    app._apply_order()
    app._on_selection_changed()


def persist_setting(app, field: str, value) -> None:
    """
    Escribe UN campo, en el espejo y en el disco.

    Uno, y no `app._settings` entero: Cuentas y Tiendas comparten ese
    diccionario, y volcarlo completo desde uno arrastraría al disco lo que se
    acabara de tocar en el otro.

    No se avisa por pantalla. Con el guardado por elemento sería un aviso por
    pulsación, y la fila ya enseña su valor nuevo: esa es la confirmación.
    """
    app._settings[field] = value
    manager = ConfigManager()
    setattr(manager.get, field, value)
    manager.save()
    logger.info(f"gui3d: guardado {field}")
