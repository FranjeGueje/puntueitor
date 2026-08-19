#!/usr/bin/env python
"""
Genera las capturas del carrusel 3D que salen en el README.

    python tools/capturas3d.py [--salida docs/screenshots]

Se dibuja SIN abrir ventana (`window-type offscreen`) y se vuelca el buffer
con `win.save_screenshot`, así que funciona por SSH y no interrumpe lo que
estés haciendo. Sale igual que en pantalla: carátulas, reflejos, ficha y
barra de ayuda.

Trabaja sobre un `HOME` temporal con COPIAS de tus bases de datos, para no
tocar nada tuyo: la aplicación escribe su estado (`gui3d.json`) al arrancar y
sería una pena que una captura te cambiara los filtros. La caché de carátulas
se ENLAZA en vez de copiarse — son 29 MB y solo se lee.

Rehacerlas cuando cambie la interfaz es volver a ejecutar esto.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Cuántos frames se dejan correr antes de disparar. Las carátulas de
#: alrededor de la selección se piden al navegar y llegan por hilos (ver
#: `covers.CoverLoader`), y las cajas entran con una animación: disparar
#: antes deja cajas de color plano y a medio colocar.
FRAMES_DE_ASENTAMIENTO = 90

#: Los mismos entre captura y captura, que solo hay que recolocar menús.
FRAMES_ENTRE_CAPTURAS = 20

#: A cuánto se reducen antes de guardarlas. Se dibuja a 1920 —el HUD se
#: reparte por el ancho, así que a menos resolución el texto sale más
#: apretado— y se baja después: el README las enseña a 800 de ancho.
ANCHO_FINAL = 1280

#: Y a paleta de 256 colores: pasan de 780 KB a 256 KB sin diferencia
#: apreciable (comprobado comparando las dos). Necesita ImageMagick; sin él
#: se guardan a tamaño completo y no pasa nada más.
COLORES_FINALES = 256


def _sandbox() -> Path:
    """Un HOME de mentira con tus datos, para no escribir en el de verdad."""
    real = Path.home()
    caja = Path(tempfile.mkdtemp(prefix="puntueitor-capturas-"))

    (caja / ".config" / "puntueitor").mkdir(parents=True)
    (caja / ".local" / "share" / "puntueitor").mkdir(parents=True)
    (caja / ".local" / "state").mkdir(parents=True)
    (caja / ".cache" / "puntueitor").mkdir(parents=True)

    datos = real / ".local" / "share" / "puntueitor"
    for nombre in ("puntueitor.db", "library.sqlite"):
        if (datos / nombre).exists():
            shutil.copy(datos / nombre, caja / ".local" / "share" / "puntueitor" / nombre)

    # Enlace, no copia: son 29 MB de JPEG que solo se leen.
    caratulas = real / ".cache" / "puntueitor" / "covers"
    if caratulas.exists():
        (caja / ".cache" / "puntueitor" / "covers").symlink_to(caratulas)

    # Las cuatro tiendas activadas: las desmarcadas no se ven (ver
    # `library_ops.is_in_active_stores`) y saldría media biblioteca.
    (caja / ".config" / "puntueitor" / "config.json").write_text(
        '{"steam_is_active": true, "gog_is_active": true,'
        ' "epic_is_active": true, "amazon_is_active": true}\n'
    )
    return caja


def _preparar_entorno() -> Path:
    caja = _sandbox()
    os.environ.update(
        HOME=str(caja),
        XDG_CONFIG_HOME=str(caja / ".config"),
        XDG_DATA_HOME=str(caja / ".local" / "share"),
        XDG_STATE_HOME=str(caja / ".local" / "state"),
        XDG_CACHE_HOME=str(caja / ".cache"),
    )
    return caja


def _juego_con_ficha(app, titulo: str | None = None):
    """
    Un juego con datos que enseñar: carátula ya en disco, duración y notas.

    La ficha con medio campo a N/A no dice nada de lo que hace el programa.
    Con `titulo` se elige a mano, que es lo práctico para que el fondo —la
    carátula del seleccionado, desenfocada— tenga algo de color.
    """
    if titulo:
        buscado = titulo.casefold()
        elegido = next(
            (e for e in app.entries if e.title.casefold() == buscado), None,
        )
        if elegido is None:
            elegido = next(
                (e for e in app.entries if buscado in e.title.casefold()), None,
            )
        if elegido is not None:
            return elegido
        print(f"  (no encontré {titulo!r}; elijo uno con la ficha completa)")

    def puntuacion(entry):
        juego = entry.game
        if juego is None:
            return -1
        return sum((
            entry.key not in app._pending_covers,     # carátula ya cargada
            bool(juego.duration_hours),
            bool(juego.steamdb_score),
            bool(juego.storyline),
            bool(juego.genres),
        ))

    return max(app.entries, key=puntuacion)


def _pasar_frames(app, cuantos: int) -> None:
    for _ in range(cuantos):
        app.task_mgr.step()


def _encoger(ruta: Path) -> None:
    """Reduce, baja la paleta y limpia metadatos, si hay ImageMagick."""
    # `magick` es el binario de la versión 7; `convert` sigue existiendo pero
    # avisa de que está obsoleto en cada llamada.
    magick = shutil.which("magick") or shutil.which("convert")
    if magick is None:
        print("  (sin ImageMagick: se quedan a tamaño completo)")
        return
    subprocess.run(
        [magick, str(ruta), "-resize", f"{ANCHO_FINAL}x",
         "-colors", str(COLORES_FINALES), "-strip", str(ruta)],
        check=False, capture_output=True,
    )


def _disparar(app, destino: Path, nombre: str) -> None:
    from panda3d.core import Filename

    ruta = destino / nombre
    ok = app.win.save_screenshot(Filename.from_os_specific(str(ruta)))
    if ok:
        _encoger(ruta)
    tamano = ruta.stat().st_size // 1024 if ruta.exists() else 0
    print(f"  {'✓' if ok else '✗'} {nombre}  ({tamano} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--salida", default=str(RAIZ / "docs" / "screenshots"),
        help="dónde dejar los PNG (por defecto docs/screenshots)",
    )
    parser.add_argument(
        "--ancho", type=int, default=1920,
    )
    parser.add_argument(
        "--alto", type=int, default=1080,
    )
    parser.add_argument(
        "--juego", default=None,
        help="qué juego protagoniza las capturas (por defecto, uno con la "
             "ficha completa)",
    )
    args = parser.parse_args()

    destino = Path(args.salida).resolve()
    destino.mkdir(parents=True, exist_ok=True)

    caja = _preparar_entorno()
    print(f"entorno temporal: {caja}")

    from panda3d.core import loadPrcFileData

    loadPrcFileData("", f"window-type offscreen\nwin-size {args.ancho} {args.alto}\n")
    sys.path.insert(0, str(RAIZ))

    import logging

    logging.disable(logging.INFO)
    from puntueitor.gui3d.app import App

    app = App()
    print(f"biblioteca: {len(app.entries)} juegos")

    # Colocarse en un juego que luzca, y esperar a que llegue su carátula.
    elegido = _juego_con_ficha(app, args.juego)
    while app.carousel.selected.key != elegido.key:
        app.carousel.move(1)
    app._on_selection_changed()
    _pasar_frames(app, FRAMES_DE_ASENTAMIENTO)
    print(f"juego elegido: {app.carousel.selected.title!r}\n")

    _disparar(app, destino, "gui3d-main.png")

    app._open_game_menu()
    _pasar_frames(app, FRAMES_ENTRE_CAPTURAS)
    _disparar(app, destino, "gui3d-juego.png")
    app._close_all_menus()

    app._open_scoring_menu()
    _pasar_frames(app, FRAMES_ENTRE_CAPTURAS)
    _disparar(app, destino, "gui3d-scoring.png")
    app._close_all_menus()

    # Opciones -> Avanzado, con sus dos secciones.
    app._push_menu(app.advanced_menu)
    _pasar_frames(app, FRAMES_ENTRE_CAPTURAS)
    _disparar(app, destino, "gui3d-avanzado.png")
    app._close_all_menus()

    # El aviso de regenerar, SIN confirmarlo: solo se abre la pregunta.
    app._confirm_regenerate()
    _pasar_frames(app, FRAMES_ENTRE_CAPTURAS)
    _disparar(app, destino, "gui3d-regenerar.png")
    app._close_all_menus()

    # Cuentas: credenciales y sesiones de tienda. Se abre por su método de
    # verdad y no empujando el menú, porque es quien lo rellena con los
    # valores en edición y el estado de cada sesión.
    app._open_accounts_menu()
    _pasar_frames(app, FRAMES_ENTRE_CAPTURAS)
    _disparar(app, destino, "gui3d-cuentas.png")
    app._close_all_menus()

    # Tiendas: qué se carga. Es el otro medio de la antigua "Configuración".
    app._open_settings_menu()
    _pasar_frames(app, FRAMES_ENTRE_CAPTURAS)
    _disparar(app, destino, "gui3d-tiendas.png")
    app._close_all_menus()

    app._push_menu(app.credits_menu)
    _pasar_frames(app, FRAMES_ENTRE_CAPTURAS)
    _disparar(app, destino, "gui3d-creditos.png")
    app._close_all_menus()

    # El Editor Rápido: lo que cambia es la barra de ayuda de abajo, así que
    # se entra al modo y se retrata el carrusel tal cual.
    app._toggle_editor_mode()
    _pasar_frames(app, FRAMES_ENTRE_CAPTURAS)
    _disparar(app, destino, "gui3d-editor.png")
    app._toggle_editor_mode()

    print(f"\nlisto: {destino}")
    shutil.rmtree(caja, ignore_errors=True)


if __name__ == "__main__":
    main()
