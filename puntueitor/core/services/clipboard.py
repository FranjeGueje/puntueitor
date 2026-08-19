"""
Leer el portapapeles del sistema.

Existe porque Panda3D no lo expone: no hay nada en `panda3d.core` ni en
`DirectEntry` que dé acceso al portapapeles, así que el carrusel no tendría
forma de pegar la URL enorme con la que termina el login de cada tienda —y
teclearla a mano con un mando no es una opción.

Lo que NO se usa, y por qué, para que nadie lo "arregle" luego:

- `tkinter` (biblioteca estándar, `Tk().clipboard_get()`) no vale por sí
  sola: en un equipo sin el paquete `tk` del sistema ni siquiera importa
  (`libtk8.6.so: cannot open shared object file`), que es justamente el caso
  en el que se probó esto.
- `pyperclip` tampoco resuelve nada en Linux: no lee el portapapeles, delega
  en `xclip`/`xsel`/`wl-clipboard` o en bindings de Qt/GTK. Sería una
  dependencia más que fallaría en los mismos sitios.

Así que se pregunta a lo que ya está instalado, en orden, y se usa lo primero
que conteste. Las dos últimas vías son Klipper —el portapapeles de KDE— por
D-Bus, y son las que hacen que esto funcione en un Plasma recién instalado
SIN INSTALAR NADA: `gdbus` viene con `glib2` y Klipper con el propio Plasma.

Hay un caso que no se cubre y no se disimula: el modo juego del Deck
(gamescope) no tiene ni Klipper ni `wl-paste`. Allí no habrá pegado, y lo que
toca es decirlo, no fallar en silencio.
"""
import ast
import logging

logger = logging.getLogger(__name__)

#: Cuánto se espera a cada herramienta. Son todas locales e instantáneas; si
#: una se cuelga, lo que no puede pasar es que se lleve por delante el
#: carrusel, que está esperando a pintar el siguiente fotograma.
TIMEOUT = 3


def _crudo(salida: str) -> str:
    """La mayoría escupe el contenido tal cual."""
    return salida


def _gvariant(salida: str) -> str:
    """
    Lo que devuelve `gdbus`, que es GVariant: `('el texto',)`.

    `literal_eval` lo lee bien —incluidas comillas, apóstrofos y saltos de
    línea escapados dentro— y, al no ser `eval`, no ejecuta nada de lo que
    venga. El desmontaje a mano queda de respaldo por si algún día la salida
    deja de parecerse a una tupla de Python.
    """
    texto = salida.strip()
    try:
        valor = ast.literal_eval(texto)
    except (ValueError, SyntaxError):
        return texto.removeprefix("('").removesuffix("',)")

    if isinstance(valor, tuple) and valor:
        return str(valor[0])
    return str(valor)


#: Cómo se le pide el portapapeles a cada cosa, en orden de preferencia.
#: Primero las herramientas dedicadas —si están, son la respuesta correcta
#: sea cual sea el escritorio— y después Klipper, que es específico de KDE
#: pero no hay que instalarlo.
FUENTES: tuple[tuple[str, tuple[str, ...], object], ...] = (
    ("wl-clipboard", ("wl-paste", "--no-newline"), _crudo),
    ("xclip", ("xclip", "-selection", "clipboard", "-o"), _crudo),
    ("xsel", ("xsel", "--clipboard", "--output"), _crudo),
    ("klipper", ("qdbus6", "org.kde.klipper", "/klipper",
                 "getClipboardContents"), _crudo),
    ("klipper", ("qdbus", "org.kde.klipper", "/klipper",
                 "getClipboardContents"), _crudo),
    ("klipper", ("gdbus", "call", "--session", "--dest", "org.kde.klipper",
                 "--object-path", "/klipper", "--method",
                 "org.kde.klipper.klipper.getClipboardContents"), _gvariant),
)

SIN_PORTAPAPELES = (
    "no se ha podido leer el portapapeles: no hay ninguna forma de "
    "consultarlo en esta sesión"
)


def normalize(texto: str) -> str:
    """
    Deja el texto en condiciones de entrar en un campo de una sola línea.

    Los saltos de línea importan más de lo que parece: una URL copiada del
    navegador suele venir con uno detrás, y dentro de un `DirectEntry` de
    `numLines=1` no se ve —pero viaja igual al canjear el código y la tienda
    lo rechaza sin que se entienda por qué.
    """
    return " ".join((texto or "").split())


def read_clipboard() -> tuple[str, str]:
    """
    El contenido del portapapeles, o el motivo de no haberlo conseguido.

    Devuelve `(texto, motivo)`: uno de los dos siempre viene vacío. Como el
    resto de `core/services`, NO LANZA — esto lo llama la interfaz, muchas
    veces desde un hilo, y una excepción cruzando esa frontera es un cierre
    en seco.
    """
    # Dentro: `subprocess` no hace falta para arrancar, y esto se llama solo
    # cuando alguien pulsa pegar.
    import subprocess

    for nombre, comando, parser in FUENTES:
        try:
            resultado = subprocess.run(
                list(comando), capture_output=True, text=True, timeout=TIMEOUT,
            )
        except FileNotFoundError:
            # No está instalado. Es el caso normal: se prueban varias
            # precisamente porque no se sabe cuál habrá.
            continue
        except subprocess.TimeoutExpired:
            logger.debug(f"{comando[0]} no contestó en {TIMEOUT}s")
            continue
        except Exception as error:  # noqa: BLE001 - se prueba la siguiente
            # Ancho a propósito. Esto se llama desde el hilo que pinta el
            # carrusel, y lo peor que puede hacer una herramienta rara del
            # sistema es tumbar la aplicación por no poder pegar: si una vía
            # falla de cualquier forma, se prueba la siguiente.
            logger.debug(f"no se pudo ejecutar {comando[0]}: {error}")
            continue

        if resultado.returncode != 0:
            # Pasa a diario y no es un fallo: `qdbus6` existe en cualquier
            # equipo con Qt, pero contesta con error si no hay Klipper.
            logger.debug(
                f"{comando[0]} devolvió {resultado.returncode}: "
                f"{(resultado.stderr or '').strip()[:120]}"
            )
            continue

        texto = normalize(parser(resultado.stdout or ""))
        if texto:
            logger.debug(f"portapapeles leído con {nombre} ({len(texto)} caracteres)")
            return texto, ""

        # Contestó bien pero no había nada. No se sigue probando: la vía
        # funciona, el portapapeles está vacío, y preguntarle a otra
        # devolvería algo más viejo.
        return "", "el portapapeles está vacío"

    logger.info(
        "ninguna forma de leer el portapapeles: se probó "
        + ", ".join(comando[0] for _, comando, _ in FUENTES)
    )
    return "", SIN_PORTAPAPELES
