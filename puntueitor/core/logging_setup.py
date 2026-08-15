"""
Configurar el log, igual para las dos interfaces.

Estaba en cada punto de entrada y no de la misma forma: la TUI escribía al
fichero con `filemode="w"` —o sea, arrancar borraba justo lo que se quería
mirar— y el carrusel hacía un `basicConfig` sin fichero AL IMPORTAR su módulo,
así que todo se iba a stderr. Lanzado desde Steam, que es como se usa, eso
significa que la interfaz principal no dejaba ni una línea.

Aquí no se toca el disco por importar (misma regla que `core/paths.py`): hay
que llamar a `setup_logging` a mano, y DESPUÉS de `paths.migrate_legacy_paths()`
para no crear el log nuevo antes de que la migración pueda traerse el viejo.
"""
import logging
import logging.handlers
import platform
import sys

from puntueitor.core import paths
from puntueitor.core.diagnostics import missing_credentials

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

#: Se rota en vez de truncar: un fallo raro se suele contar a la vuelta, con
#: la aplicación ya reabierta, y con `filemode="w"` para entonces el log del
#: arranque que falló ya no existía.
MAX_BYTES = 1_000_000
BACKUP_COUNT = 2

#: Terceros que hablan demasiado. Van a WARNING para que subir NUESTRO nivel a
#: DEBUG siga siendo legible: sin esto, investigar algo entierra el log bajo
#: el detalle HTTP de cada una de las mil peticiones.
NOISY = ("urllib3", "requests", "igdbpy", "PIL", "charset_normalizer", "asyncio")


def setup_logging(frontend: str, level: int = logging.INFO, console: bool = False) -> None:
    """
    Deja el logging listo para escribir en `paths.log_file()`.

    `console` solo lo pide el carrusel: la TUI se dibuja sobre el terminal y
    escribir ahí le rompe la pantalla.
    """
    log_path = paths.log_file()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    # Se limpia lo que hubiera: si algún módulo llamó a `basicConfig` al
    # importarse, su handler a stderr seguiría ahí duplicando cada línea.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if console:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        root.addHandler(stream)

    for name in NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

    _log_session_header(frontend)


def _log_session_header(frontend: str) -> None:
    """
    Cuatro líneas al arrancar con lo que explica la mayoría de los "no me
    salen los juegos": qué tiendas están activas, qué credenciales faltan y de
    dónde se van a leer las bibliotecas de Heroic.

    Se escribe SIEMPRE, no solo cuando algo falla: cuando el usuario cuenta un
    problema, esto ya está en su log sin tener que pedirle que lo reproduzca.

    Nunca se registra el VALOR de una credencial, solo si está o no está: el
    log se comparte para pedir ayuda y acabaría con la API key dentro.
    """
    logger.info(
        f"=== Puntueitor [{frontend}] · Python {platform.python_version()} "
        f"· {platform.system()} {platform.release()} ==="
    )

    try:
        from puntueitor.core.config import ConfigManager
        config = ConfigManager().get
    except Exception as error:  # noqa: BLE001 - sin config se sigue arrancando
        logger.warning(f"no se pudo leer la configuración: {error}")
        return

    activas = [
        nombre for nombre, activa in (
            ("Steam", config.steam_is_active), ("GOG", config.gog_is_active),
            ("Epic", config.epic_is_active), ("Amazon", config.amazon_is_active),
        ) if activa
    ]
    logger.info(f"Tiendas activas: {', '.join(activas) if activas else 'NINGUNA'}")
    if not activas:
        logger.warning(
            "no hay ninguna tienda activa: no se cargará ningún juego "
            "(Opciones → Configuración)"
        )

    faltan = missing_credentials(config)
    if faltan:
        logger.warning(
            f"faltan credenciales: {', '.join(faltan)}. "
            "Sin ellas esas tiendas no se pueden consultar "
            "(Opciones → Configuración)"
        )
    else:
        logger.info("Credenciales: todas configuradas")

    if config.gog_is_active or config.epic_is_active or config.amazon_is_active:
        _log_heroic_path(config)


def _log_heroic_path(config) -> None:
    """De dónde va a leer Heroic, o por qué no va a leer nada."""
    from puntueitor.core.heroics import HeroicsLoader

    ruta = HeroicsLoader().find_heroic_path(config.heroic_path or None)
    if ruta is None:
        logger.warning(
            "no se encuentra la carpeta de Heroic: GOG, Epic y Amazon no "
            "darán ningún juego (Opciones → Configuración)"
        )
    else:
        logger.info(f"Heroic: {ruta}")
