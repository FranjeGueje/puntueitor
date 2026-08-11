"""
Carga de carátulas reales para el carrusel, con caché local en disco.

Reutiliza exactamente el mismo directorio y convención de nombres que la TUI
(`gui/app.py:_download_and_show_cover`: `~/.cache/puntueitor/covers/{igdb_id}.jpg`)
para que las carátulas descargadas desde cualquiera de los dos frontends
sirvan al otro.
"""
import logging
import queue
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from panda3d.core import Filename, Texture, TexturePool

from puntueitor.core import paths

logger = logging.getLogger(__name__)


DOWNLOAD_TIMEOUT = 8


def _cover_path(igdb_id: int) -> Path:
    return COVERS_DIR / f"{igdb_id}.jpg"


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
    texture = TexturePool.load_texture(Filename.from_os_specific(str(path)))
    if texture is None:
        logger.warning(f"gui3d: carátula corrupta o ilegible: {path}")
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
    """
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    path = _cover_path(igdb_id)
    try:
        urllib.request.urlretrieve(cover_url, path)
    except Exception as e:
        logger.warning(f"gui3d: no se pudo descargar la carátula {igdb_id}: {e}")
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
    """

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._done: queue.Queue[tuple[object, Path]] = queue.Queue()
        self._requested: set[object] = set()
        self._inflight = 0
        self._inflight_lock = threading.Lock()

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
        self._executor.submit(self._download, key, igdb_id, cover_url)

    def _download(self, key: object, igdb_id: int, cover_url: str) -> None:
        try:
            path = download_cover(igdb_id, cover_url)
            if path is not None:
                self._done.put((key, path))
        finally:
            # En `finally` para que un fallo de descarga no deje el contador
            # inflado para siempre: si se quedara alto, el relleno de fondo
            # dejaría de encolar nada y las carátulas restantes no bajarían.
            with self._inflight_lock:
                self._inflight -= 1

    def poll(self) -> list[tuple[object, Texture]]:
        """
        Texturas recién descargadas desde la última llamada, como
        `(key, texture)`. Pensado para llamarse una vez por frame.
        """
        results = []
        while True:
            try:
                key, path = self._done.get_nowait()
            except queue.Empty:
                break
            texture = _load_texture(path)
            if texture is not None:
                results.append((key, texture))
        return results

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
