"""
Copias de seguridad desde el carrusel: pedir la ruta, avisar y cerrar.

Primer trozo que sale de `gui3d/app.py`, que tenía 148 métodos en una sola
clase. Se empieza por aquí porque es lo que menos toca el resto: no sabe del
carrusel, ni de los menús, ni del mando — solo pide una ruta, llama al
servicio del core y enseña el resultado.

**No son métodos sueltos en otro fichero.** Reciben la aplicación como
argumento explícito (`app`), así que se ve de un vistazo qué necesitan de
ella: `_open_text_prompt`, `_ask_confirm` y `notifier`. Y la parte que es
decisión de verdad —qué ruta se ha pedido, qué mensaje se enseña— son
funciones puras que se prueban sin abrir ninguna ventana.

Lo que hace el trabajo sigue estando en `core/services/backup.py`. Aquí solo
está la conversación con el usuario.
"""
import logging
import os
from pathlib import Path

from puntueitor.core.services import backup
from puntueitor.gui3d import menus

logger = logging.getLogger(__name__)


# ──────────────────────────────
# Decisiones (sin ventana, y por eso con test)
# ──────────────────────────────

def parse_path(texto: str) -> Path | None:
    """
    La ruta que ha escrito el usuario, o None si no ha escrito ninguna.

    Aceptar la cadena vacía sería crear un fichero llamado "" o restaurar
    desde el directorio actual; devolver None deja que quien llama no haga
    nada, que es lo que espera alguien que borra el texto y acepta.
    """
    limpio = (texto or "").strip()
    return Path(limpio) if limpio else None


def backup_message(resultado) -> str:
    """Lo que se enseña cuando la copia sale bien."""
    return (
        f"Copia guardada: {resultado.path.name} "
        f"({resultado.megabytes:.1f} MB)"
    )


# ──────────────────────────────
# Los pasos, con la aplicación delante
# ──────────────────────────────

def ask_backup_path(app) -> None:
    """
    Opciones -> Avanzado -> Copia de seguridad.

    Se propone el escritorio ya escrito, que es lo que hace que esto se pueda
    usar con el mando sin escribir una ruta entera: basta con aceptar. Esc o B
    cancelan sin hacer nada, como en cualquier otro cuadro de texto.
    """
    app._open_text_prompt(
        title=menus.BACKUP_TITLE,
        initial=str(backup.default_backup_path()),
        on_accept=lambda texto: do_backup(app, texto),
    )


def do_backup(app, texto: str) -> None:
    """
    Escribe el zip. En el hilo principal a propósito: con la biblioteca real
    son un par de segundos (casi todo el peso son carátulas), no los minutos
    de una actualización, y montar otro trabajador para eso sería más código
    del que ahorra.
    """
    ruta = parse_path(texto)
    if ruta is None:
        return
    try:
        resultado = backup.create_backup(ruta)
    except backup.BackupError as error:
        logger.warning(f"gui3d: no se pudo copiar: {error}")
        app.notifier.show(str(error))
        return
    app.notifier.show(backup_message(resultado))


def ask_restore_path(app) -> None:
    """Opciones -> Avanzado -> Restaurar copia: primero la ruta."""
    app._open_text_prompt(
        title=menus.BACKUP_TITLE_RESTORE,
        initial=str(backup.default_backup_path()),
        on_accept=lambda texto: confirm_restore(app, texto),
    )


def confirm_restore(app, texto: str) -> None:
    """
    Y después la confirmación, que aquí no es un trámite: restaurar
    sobrescribe la biblioteca, los estados y las claves.
    """
    ruta = parse_path(texto)
    if ruta is None:
        return
    app._ask_confirm(
        menus.RESTORE_CONFIRM_TITLE,
        menus.RESTORE_WARNING + menus.RESTORE_NOTE,
        menus.RESTORE_YES,
        lambda: do_restore(app, ruta),
        warning=len(menus.RESTORE_WARNING),
    )


def do_restore(app, ruta: Path) -> None:
    """
    Restaura y CIERRA EN SECO, con `os._exit`.

    Lo de cerrar no es una comodidad: los ficheros se acaban de reescribir por
    debajo de una aplicación que sigue viva, y seguir aquí sería trabajar con
    datos que ya no están en disco.

    Y lo de cerrar así, sin el `userExit()` de siempre, tampoco: un cierre
    ordenado ESCRIBE. Guarda los filtros del carrusel encima del `gui3d.json`
    recién restaurado, y las conexiones SQLite abiertas consolidan su estado
    al cerrarse. `os._exit` no ejecuta `atexit` ni destructores, así que nadie
    escribe nada más — que es justo lo que se necesita cuando lo que hay en
    disco es lo bueno.

    `restore_backup` ya deja los ficheros a salvo por su cuenta (escribe en
    inodos nuevos), así que esto es el segundo cinturón, no el único.
    """
    try:
        resultado = backup.restore_backup(ruta)
    except backup.BackupError as error:
        logger.warning(f"gui3d: no se pudo restaurar: {error}")
        app.notifier.show(str(error))
        return
    logger.info(f"gui3d: copia restaurada ({resultado.files} ficheros), cerrando")
    logging.shutdown()
    os._exit(0)
