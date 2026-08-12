"""
Carga de carátulas reales para el carrusel, con caché local en disco.

Reutiliza exactamente el mismo directorio y convención de nombres que la TUI
(`gui/app.py:_download_and_show_cover`: `~/.cache/puntueitor/covers/{igdb_id}.jpg`)
para que las carátulas descargadas desde cualquiera de los dos frontends
sirvan al otro.
"""
import logging
import os
import queue
import shutil
import threading
import urllib.request
from pathlib import Path

from panda3d.core import Filename, Texture

from puntueitor.core import paths

logger = logging.getLogger(__name__)


#: Segundos de espera por descarga. `urlretrieve` NO acepta timeout, así que
#: durante mucho tiempo esta constante estuvo declarada pero sin usar y las
#: descargas se quedaban esperando indefinidamente si el servidor no
#: respondía. Por eso se baja el fichero con `urlopen(..., timeout=...)` a
#: mano en vez de con `urlretrieve`.
DOWNLOAD_TIMEOUT = 8

#: Cada cuánto comprueba un hilo de descarga si le han pedido parar mientras
#: espera trabajo. Corto para que `shutdown()` tenga efecto enseguida, pero
#: no tanto como para que despertarse salga caro estando la cola vacía.
_WORKER_POLL_TIMEOUT = 0.2


def _cover_path(igdb_id: int) -> Path:
    return paths.covers_dir() / f"{igdb_id}.jpg"


def _load_texture(path: Path) -> Texture | None:
    """
    Carga una carátula desde disco con el filtrado adecuado para el
    carrusel.

    En el carrusel la carátula casi siempre se ve MÁS PEQUEÑA que su
    resolución real (una imagen de ~264 px de ancho ocupa ~110 px en
    pantalla, y menos aún en las cajas laterales giradas). Con el filtro por
    defecto de Panda3D — lineal, sin mipmaps — reducir así muestrea la
    textura de forma irregular y el arte "hierve" y aparece dentado al
    moverse el carrusel: se parece mucho a falta de antialiasing, pero es
    aliasing de textura y el MSAA no lo toca (el MSAA suaviza los bordes de
    la geometría, no el interior de las caras). Mipmaps + filtrado
    anisotrópico sí lo arreglan, y el anisotrópico importa especialmente
    aquí porque las cajas laterales se ven muy escorzadas.
    """
    # `Texture().read(...)`, NO `TexturePool.load_texture(...)`. TexturePool
    # cachea por nombre de fichero y, verificado en runtime, no vuelve a leer
    # del disco aunque el contenido cambie por debajo con el mismo nombre:
    # cargar el mismo `{igdb_id}.jpg` dos veces devuelve el mismísimo objeto
    # Texture de la primera vez, corrupto incluido, sin importar que el
    # fichero se haya borrado y regenerado entre medias. Como cada
    # `igdb_id` es siempre el mismo nombre de fichero para siempre (por
    # diseño, para compartir caché con la TUI), ese comportamiento convertía
    # un solo fallo de lectura en un fallo PERMANENTE para ese juego durante
    # el resto de la sesión — el borrado de más abajo no arreglaba nada
    # porque el problema nunca estuvo en el disco, sino en la caché interna
    # de Panda3D. Un `Texture()` nuevo por lectura sí relee el disco siempre.
    texture = Texture()
    if not texture.read(Filename.from_os_specific(str(path))):
        logger.warning(f"gui3d: carátula corrupta o ilegible: {path}")
        # Se borra para que la próxima vez `get_cached_cover_path` no la
        # vea y se reintente la descarga. Sin esto, un fichero realmente
        # corrupto (que con el renombrado atómico de `download_cover` ya no
        # debería producirse, pero por si acaso: disco lleno a mitad de
        # escritura, conexión cortada sin que `urlretrieve` lo detecte) se
        # queda ahí para siempre — "existe" así que nunca se vuelve a bajar.
        path.unlink(missing_ok=True)
        return None

    texture.set_minfilter(Texture.FT_linear_mipmap_linear)
    texture.set_magfilter(Texture.FT_linear)
    texture.set_anisotropic_degree(16)
    return texture


def get_cached_cover_path(igdb_id: int) -> Path | None:
    """Ruta a la carátula si ya está en caché local, o None."""
    path = _cover_path(igdb_id)
    return path if path.exists() else None


def download_cover(igdb_id: int, cover_url: str) -> Path | None:
    """
    Descarga la carátula a la caché local. Best-effort: cualquier fallo de
    red devuelve None en vez de propagar, para no tumbar el arranque del
    carrusel por un juego sin conexión.

    Se descarga a un fichero temporal en el mismo directorio y se renombra
    al final con `os.replace` (atómico dentro del mismo sistema de
    ficheros), en vez de escribir directamente sobre `{igdb_id}.jpg` con
    `urlretrieve`. La versión directa deja el fichero destino visible y
    "existente" desde el primer byte escrito: cualquiera que compruebe
    `path.exists()` mientras la descarga está en curso —y aquí hay más de
    un sitio que lo hace desde el hilo principal, sin pasar por
    `CoverLoader`, ver `app.App._request_nearby_covers`— encuentra un JPEG
    a medias y Panda3D falla al decodificarlo ("Texture exists but cannot
    be read"). Con el renombrado atómico, `path.exists()` es False hasta
    que el fichero está completo: no hay ventana en la que se pueda leer a
    medias.
    """
    paths.covers_dir().mkdir(parents=True, exist_ok=True)
    path = _cover_path(igdb_id)
    # Sufijo con el id de hilo: dos descargas de carátulas DISTINTAS nunca
    # chocan (rutas distintas), pero si alguna vez se pidiera la misma
    # `igdb_id` dos veces en paralelo, un nombre temporal fijo compartido
    # sí podría pisarse entre sí.
    tmp_path = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    try:
        with urllib.request.urlopen(cover_url, timeout=DOWNLOAD_TIMEOUT) as response:
            with open(tmp_path, "wb") as tmp_file:
                shutil.copyfileobj(response, tmp_file)
        os.replace(tmp_path, path)
    except Exception as e:
        logger.warning(f"gui3d: no se pudo descargar la carátula {igdb_id}: {e}")
        tmp_path.unlink(missing_ok=True)
        return None
    return path


def load_cover_texture(
    igdb_id: int,
    cover_url: str | None,
    *,
    allow_download: bool = True,
) -> Texture | None:
    """
    Textura de la carátula de un juego, cacheada en disco. Devuelve None si
    no hay carátula en caché ni se pudo descargar — el llamante decide el
    color de relleno.
    """
    path = get_cached_cover_path(igdb_id)

    if path is None and allow_download and cover_url:
        path = download_cover(igdb_id, cover_url)

    if path is None:
        return None

    return _load_texture(path)


class CoverLoader:
    """
    Descarga carátulas en segundo plano sin bloquear el hilo de render.

    Todas las llamadas a la API de Panda3D (incluida `TexturePool`) deben
    hacerse desde el hilo principal, así que los hilos de descarga solo
    tocan el disco (`urllib` + escritura de fichero); `poll()` se llama desde
    una tarea del `task_mgr` en el hilo principal y es ahí donde se carga la
    textura y se le entrega al llamante.

    Los hilos son PROPIOS y `daemon=True`, no un `ThreadPoolExecutor`. El
    executor parecía la opción obvia, pero sus hilos son no-daemon y además
    `concurrent.futures` registra un `atexit` que los ESPERA a todos al
    cerrar el intérprete. Resultado: al cerrar la ventana, el proceso se
    quedaba colgado hasta que terminara la última descarga en curso — y sin
    timeout (ver `DOWNLOAD_TIMEOUT`), para siempre si el servidor no
    contestaba. Ni `shutdown(wait=False, cancel_futures=True)` lo evita: eso
    cancela lo ENCOLADO, pero no interrumpe lo que ya se está descargando.
    Con hilos daemon, el intérprete no los espera y el proceso se cierra al
    instante; una descarga a medias no deja basura porque el fichero se
    escribe en un temporal y solo se renombra al terminar (ver
    `download_cover`).
    """

    def __init__(self, max_workers: int = 4):
        self._pending: queue.Queue[tuple[object, int, str]] = queue.Queue()
        self._done: queue.Queue[tuple[object, Path]] = queue.Queue()
        self._requested: set[object] = set()
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self._stop = threading.Event()
        self._workers = [
            threading.Thread(
                target=self._worker, name=f"cover-loader-{i}", daemon=True,
            )
            for i in range(max_workers)
        ]
        for worker in self._workers:
            worker.start()

    @property
    def inflight(self) -> int:
        """Descargas encoladas o en curso todavía sin terminar."""
        with self._inflight_lock:
            return self._inflight

    def request(self, key: object, igdb_id: int, cover_url: str | None) -> None:
        """
        Encola la descarga de la carátula de `igdb_id`, asociada a `key`.

        Repetir la petición de una `key` ya pedida no hace nada. Importa
        porque quien llama pide las carátulas de alrededor de la selección
        cada vez que se navega, y las ventanas de dos posiciones contiguas
        se solapan casi por completo: sin esto, moverse por el carrusel
        volvería a encolar los mismos juegos una y otra vez.
        """
        if not cover_url or key in self._requested:
            return
        self._requested.add(key)
        with self._inflight_lock:
            self._inflight += 1
        self._pending.put((key, igdb_id, cover_url))

    def _worker(self) -> None:
        """
        Bucle de un hilo de descarga: coge peticiones y las baja.

        La espera en la cola lleva timeout en vez de bloquear para siempre
        porque así el hilo comprueba `_stop` de vez en cuando y termina solo
        tras un `shutdown()`, sin necesidad de despertarlo con centinelas.
        """
        while not self._stop.is_set():
            try:
                key, igdb_id, cover_url = self._pending.get(timeout=_WORKER_POLL_TIMEOUT)
            except queue.Empty:
                continue
            try:
                if self._stop.is_set():
                    # Se ha pedido cerrar mientras esta petición esperaba en
                    # la cola: ya no le interesa a nadie.
                    continue
                # Puede estar ya en disco (descargada en otra sesión, o por
                # la TUI, que usa el mismo directorio). Entonces no hay nada
                # que bajar y se anuncia directamente.
                path = get_cached_cover_path(igdb_id) or download_cover(igdb_id, cover_url)
                if path is not None:
                    self._done.put((key, path))
            finally:
                # En `finally` para que un fallo de descarga no deje el
                # contador inflado para siempre: si se quedara alto, el
                # relleno de fondo dejaría de encolar nada y las carátulas
                # restantes no bajarían.
                with self._inflight_lock:
                    self._inflight -= 1

    def poll(self) -> list[tuple[object, Path]]:
        """
        Carátulas que han llegado a disco desde la última llamada, como
        `(key, ruta)`. Pensado para llamarse una vez por frame.

        Devuelve RUTAS, no texturas, a propósito: crear la textura cuesta
        3,4 ms y solo merece la pena para las cajas que se van a ver. Quien
        llama decide (`app.App._on_cover_ready`); si el juego está lejos de
        la selección, basta con que su fichero quede en disco y ya se
        cargará cuando toque.
        """
        results = []
        while True:
            try:
                results.append(self._done.get_nowait())
            except queue.Empty:
                break
        return results

    def shutdown(self) -> None:
        """
        Pide a los hilos que paren. NO los espera: son daemon justamente
        para que cerrar la aplicación sea inmediato aunque haya descargas a
        medias (ver la nota de la clase).
        """
        self._stop.set()
