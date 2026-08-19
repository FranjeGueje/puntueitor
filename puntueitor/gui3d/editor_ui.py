"""
El Editor Rápido: marcar estados con el stick derecho, sin abrir menús.

Cuarto trozo que sale de `gui3d/app.py`. Más pequeño de lo que parecía en un
principio: el bloque de comentario `# ── Editor Rápido ──` en el fichero
original incluía también varios métodos del modo Desconocidos, que no son de
aquí.

Dos cosas se quedan en `App` a propósito, aunque solo las usa el editor y el
menú de juego:

- `_blocked_in_editor` es una guarda que se llama desde seis sitios
  repartidos por todo el fichero (abrir Opciones, Puntueitor, Filtrar, el
  menú del juego, Actualizar, Desconocidos), no solo desde aquí.
- `_persist_flags` la comparten `editor_gesture` y `_on_game_flag_toggled`
  (que sigue en `App`): es la escritura de los cuatro estados de un juego,
  no algo propio del editor.

El módulo llama a `app._blocked_in_editor(...)` y `app._persist_flags(game)`
igual que `backup_ui` ya llama a `app._ask_confirm`.
"""
import logging

from puntueitor.gui3d import menus

logger = logging.getLogger(__name__)


def toggle_editor_mode(app) -> None:
    """
    R3 (o la tecla "e"): entra y sale del Editor Rápido.

    Solo desde el carrusel principal y sin nada abierto encima. En
    desconocidos no tiene sentido —un desconocido no tiene estados— y con
    un menú abierto el stick derecho no se está mirando.
    """
    if app._typing or app.active_menu is not None:
        return
    if app._unknown_mode:
        app.notifier.show("Editor Rápido: solo en la biblioteca")
        return

    app._editor_mode = not app._editor_mode
    # Se olvida la última posición del stick: si se sale y se entra con el
    # stick echado, el flanco tiene que volver a contarse desde cero.
    app._editor_stick = (0, 0)

    if app._editor_mode:
        app.help_text.hide()
        app.editor_help_text.show()
        app.notifier.show(menus.EDITOR_ON)
    else:
        app.editor_help_text.hide()
        app.help_text.show()
        app.notifier.show(menus.EDITOR_OFF)
        # Lo que se haya ocultado durante la sesión se aplica AHORA, al
        # salir (ver `_editor_gesture`).
        if app._hidden_filter_dirty:
            app._apply_hidden_filter()
            app._hidden_filter_dirty = False
    logger.info(f"gui3d: editor rápido {'on' if app._editor_mode else 'off'}")



def update_editor(app) -> None:
    """
    Lee el stick derecho una vez por frame, y solo actúa en el FLANCO.

    Sin esto, mantener el stick echado marcaría y desmarcaría el estado
    sesenta veces por segundo. El teclado no pasa por aquí: sus teclas ya
    son eventos sueltos.
    """
    if not app._editor_mode or app.gamepad is None:
        return
    direccion = app.gamepad.right_stick()
    if direccion == app._editor_stick:
        return
    app._editor_stick = direccion
    if direccion != (0, 0):
        editor_gesture(app, direccion)


def editor_gesture(app, direction: tuple[int, int]) -> None:
    """Una dirección del editor: conmuta el estado que le toque."""
    if not app._editor_mode or app._typing or app.active_menu is not None:
        return
    field = menus.EDITOR_FLAGS.get(direction)
    entry = app.carousel.selected
    if field is None or entry is None or entry.game is None:
        return

    game = entry.game
    nuevo = not bool(getattr(game, field))
    setattr(game, field, nuevo)
    app._persist_flags(game)
    # Con el mismo formato que el del menú de juego, y diciendo que vino
    # del editor: aquí se marca de corrido y muy rápido, así que el log
    # es la única forma de reconstruir qué se tocó si algo sale raro.
    logger.info(f"gui3d: [editor] {game.title!r}: {field} = {nuevo}")
    app.carousel.rebuild_labels(entry.key, game, app._labels_visible)
    app.notifier.show(menus.editor_notice(field, nuevo))

    if field == "hidden":
        # No se re-filtra al momento, igual que en el menú de juego: la
        # caja que acabas de marcar desaparecería de debajo y la
        # selección saltaría a otro juego mientras sigues editando. Se
        # apunta y se aplica al salir del modo.
        app._hidden_filter_dirty = True
