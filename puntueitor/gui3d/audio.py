"""
Música de fondo y efectos del carrusel.

**Los ficheros no están en el repo**: se leen de `~/.config/puntueitor/audio/`
(ver `core.paths.audio_dir`) y los pone el usuario. Así no hay que meter en
el repositorio material de terceros con su licencia a cuestas —el criterio
que sí compensó con las tipografías, que son OFL y van dentro—, y cada quien
le pone el sonido que quiera. Sin esa carpeta, el frontend arranca en
silencio exactamente igual que antes.

Formatos: Panda3D lee WAV, Ogg Vorbis y Opus de forma nativa (`WavAudio`,
`VorbisAudio` y `OpusAudio` viven dentro de `libpanda`). MIDI **no**: el
backend de audio aquí es OpenAL, que no trae sintetizador, y aunque lo
trajera el resultado dependería del banco de instrumentos de cada máquina.

Nada de aquí puede tirar la aplicación. Un fichero que falta, uno corrupto o
un sistema sin tarjeta de sonido dejan ese hueco mudo y una línea en el log;
quedarse sin frontend por un WAV roto sería absurdo.
"""
import logging
import time

from puntueitor.core import paths

logger = logging.getLogger(__name__)

#: Qué se busca y cómo se llama. Las dos extensiones se prueban en orden
#: para todos: es barato y evita el "he puesto un .ogg y no suena".
EXTENSIONS = (".ogg", ".wav")

MUSIC_NAME = "music"
ACCEPT_NAME = "accept"
BACK_NAME = "back"
MOVE_NAME = "move"

SFX_NAMES = (ACCEPT_NAME, BACK_NAME, MOVE_NAME)

#: Mínimo entre dos clics de "mover el foco". El carrusel acelera mientras
#: se mantiene la dirección hasta unos veinte pasos por segundo (ver
#: `NAV_REPEAT_MIN_INTERVAL` en `app.py`), y un clic por paso deja de ser un
#: sonido de interfaz para convertirse en una ametralladora. Con esto, al
#: girar rápido se oye un traqueteo regular en vez de un zumbido.
MOVE_MIN_INTERVAL = 0.07

#: Cuánto tiempo después de un "aceptar" se calla un "atrás".
#:
#: Un botón tiene que sonar UNA vez. Hay acciones que aplican y cierran el
#: menú en el mismo gesto —elegir un sistema de puntuación, Guardar, decir
#: que sí en una confirmación—, y esas pasan por `play_accept` y acto seguido
#: por `play_back` desde `_pop_menu`: se oían los dos clics pisándose. En vez
#: de repartir un "cierra sin sonido" por los diez sitios que cierran así, la
#: regla vive aquí, donde también valdrá para el que se añada mañana.
#:
#: El precio es que pulsar A y B a menos de esta distancia se come el
#: segundo clic. Con dos pulsaciones deliberadas no pasa; a propósito sí, y
#: es preferible a que la mitad de los menús suenen doble.
BACK_AFTER_ACCEPT = 0.12


class Audio:
    """
    Lo que suena, y a qué volumen.

    Se le pasa el cargador y los dos gestores de Panda3D en vez de sacarlos
    de `base`: son lo único que necesita de la ventana, y recibirlos permite
    probar todo esto sin abrir ninguna (ver `tests/test_gui3d_audio.py`).

    Los efectos y la música van por gestores DISTINTOS —`sfxManagerList[0]`
    y `musicManager`— y esa separación no es un detalle de implementación:
    es lo que permite subir los clics y bajar la música sin mezclar nada a
    mano.
    """

    def __init__(self, loader, sfx_manager=None, music_manager=None, clock=time.monotonic):
        self._loader = loader
        self._sfx_manager = sfx_manager
        self._music_manager = music_manager
        self._clock = clock

        self._sfx: dict[str, object] = {}
        self._last_accept = float("-inf")
        self._music = None
        # A menos infinito y no a cero: con un reloj que empieza en cero (el
        # de una prueba, o `monotonic` recién arrancado el sistema) el primer
        # movimiento caería dentro del margen y se quedaría mudo.
        self._last_move = float("-inf")

        self._load()

    # ──────────────────────────────
    # Carga
    # ──────────────────────────────

    def _load(self) -> None:
        carpeta = paths.audio_dir()
        if not carpeta.is_dir():
            # INFO y no WARNING: no tener sonido es una elección perfectamente
            # normal, no un problema que arreglar. Se dice DÓNDE se ha
            # buscado, que es lo único que hace falta para ponerlo.
            logger.info(
                f"gui3d: sin sonido (no hay carpeta {carpeta}). "
                "Ver el README para los nombres de fichero."
            )
            return

        for nombre in SFX_NAMES:
            sonido = self._cargar(carpeta, nombre, self._loader.loadSfx)
            if sonido is not None:
                self._sfx[nombre] = sonido

        self._music = self._cargar(carpeta, MUSIC_NAME, self._loader.loadMusic)
        if self._music is not None:
            self._music.setLoop(True)

        logger.info(
            f"gui3d: sonido cargado de {carpeta} "
            f"({len(self._sfx)} efectos, música {'sí' if self._music else 'no'})"
        )

    def _cargar(self, carpeta, nombre: str, cargador):
        """
        El primer fichero que exista y se pueda leer, o `None`.

        `loadSfx` no lanza cuando el fichero está corrupto o el sistema no
        tiene audio: devuelve `None` o un sonido en estado BAD. Comprobar
        solo con un `try` dejaría pasar el segundo caso y luego fallaría al
        reproducir, lejos de aquí y sin explicación.
        """
        for extension in EXTENSIONS:
            ruta = carpeta / f"{nombre}{extension}"
            if not ruta.is_file():
                continue
            try:
                sonido = cargador(str(ruta))
            except Exception as error:  # noqa: BLE001 - se cuenta, no se revienta
                logger.warning(f"gui3d: no se pudo cargar {ruta}: {error}")
                return None
            if sonido is None or not self._utilizable(sonido):
                logger.warning(f"gui3d: {ruta} no se puede reproducir")
                return None
            return sonido
        return None

    @staticmethod
    def _utilizable(sonido) -> bool:
        estado = getattr(sonido, "status", None)
        if estado is None:
            return True
        try:
            from panda3d.core import AudioSound
        except ImportError:  # pragma: no cover - solo sin Panda3D instalado
            return True
        return estado() != AudioSound.BAD

    # ──────────────────────────────
    # Volumen
    # ──────────────────────────────

    def set_volumes(self, music: int, sfx: int) -> None:
        """
        Los dos volúmenes, en porcentaje (0-100), como los guarda `state`.

        Poner la música a 0 la PARA, en vez de dejarla sonando en silencio:
        un fichero descodificándose para nada gasta CPU en un Deck, y quien
        la pone a cero la está apagando.
        """
        self._aplicar(self._music_manager, music)
        self._aplicar(self._sfx_manager, sfx)

        if self._music is None:
            return
        if music <= 0:
            self._music.stop()
        elif self._music.status() != self._music.PLAYING:
            self._music.play()

    @staticmethod
    def _aplicar(manager, porcentaje: int) -> None:
        if manager is None:
            return
        manager.setVolume(max(0, min(100, int(porcentaje))) / 100.0)

    # ──────────────────────────────
    # Reproducir
    # ──────────────────────────────

    def start_music(self, volume: int) -> None:
        self._aplicar(self._music_manager, volume)
        if self._music is not None and volume > 0:
            self._music.play()

    def play_accept(self) -> None:
        # El instante se apunta solo si ha sonado de verdad: quien no tenga
        # `accept` puesto y sí `back` tiene que seguir oyendo el suyo.
        if self._play(ACCEPT_NAME):
            self._last_accept = self._clock()

    def play_move(self) -> None:
        """El clic de mover el foco, con el freno de `MOVE_MIN_INTERVAL`."""
        ahora = self._clock()
        if ahora - self._last_move < MOVE_MIN_INTERVAL:
            return
        self._last_move = ahora
        self._play(MOVE_NAME)

    def play_back(self) -> None:
        """El clic de volver, callado si acaba de sonar el de aceptar."""
        if self._clock() - self._last_accept < BACK_AFTER_ACCEPT:
            return
        self._play(BACK_NAME)

    def _play(self, nombre: str) -> bool:
        """Reproduce el efecto si está puesto. Dice si ha sonado."""
        sonido = self._sfx.get(nombre)
        if sonido is None:
            return False
        # `play()` sobre un sonido que ya suena lo reinicia desde el
        # principio, que es justo lo que se quiere al pulsar dos veces
        # seguidas: se oyen dos clics, no uno alargado.
        sonido.play()
        return True
