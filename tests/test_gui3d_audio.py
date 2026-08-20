"""
El sonido del carrusel: qué se carga, qué se calla y cada cuánto suena.

Sin ventana de Panda3D y sin un solo fichero de audio de verdad: `Audio`
recibe el cargador, los gestores y el reloj, así que aquí se le pasan dobles.
Lo que se prueba es la política —tolerar lo que falte, no atronar al repetir,
apagar de verdad al bajar a cero—, que es lo nuestro; que un WAV suene es
cosa de Panda3D.
"""
import pytest

from puntueitor.core import paths
from puntueitor.gui3d import audio
from puntueitor.gui3d.audio import Audio


class SonidoDoble:
    def __init__(self, estado=None):
        self.reproducido = 0
        self.parado = 0
        self.en_bucle = False
        self._estado = estado
        self.PLAYING = "sonando"

    def play(self):
        self.reproducido += 1

    def stop(self):
        self.parado += 1

    def setLoop(self, valor):  # noqa: N802 - así se llama en Panda3D
        self.en_bucle = valor

    def status(self):
        return self._estado


class CargadorDoble:
    """Devuelve un sonido por ruta pedida, y apunta qué se le pidió."""

    def __init__(self, resultado=None):
        self.pedidas = []
        self._resultado = resultado

    def _cargar(self, ruta):
        self.pedidas.append(ruta)
        if self._resultado is not None:
            return self._resultado
        return SonidoDoble()

    loadSfx = _cargar
    loadMusic = _cargar


class ManagerDoble:
    def __init__(self):
        self.volumen = None

    def setVolume(self, valor):  # noqa: N802 - así se llama en Panda3D
        self.volumen = valor


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    """Una carpeta de audio vacía en el sitio donde `Audio` va a mirar."""
    destino = tmp_path / "audio"
    destino.mkdir()
    monkeypatch.setattr(paths, "audio_dir", lambda: destino)
    return destino


def _crear(carpeta, *nombres):
    for nombre in nombres:
        (carpeta / nombre).write_bytes(b"no es audio de verdad")


class TestLoQueFalta:
    def test_without_the_folder_nothing_breaks_and_nothing_plays(
        self, tmp_path, monkeypatch,
    ):
        """
        No tener sonido es una elección normal, no una avería: el frontend
        tiene que arrancar igual.
        """
        monkeypatch.setattr(paths, "audio_dir", lambda: tmp_path / "no-existe")
        cargador = CargadorDoble()

        sonido = Audio(cargador)
        sonido.play_accept()
        sonido.play_back()
        sonido.play_move()

        assert cargador.pedidas == []

    def test_an_empty_folder_is_the_same(self, carpeta):
        Audio(CargadorDoble()).play_accept()

    def test_a_file_that_cannot_be_read_leaves_only_that_gap(self, carpeta):
        """
        Un fichero corrupto silencia SU efecto, no los demás ni la
        aplicación entera.
        """
        _crear(carpeta, "accept.wav", "back.wav")

        class SoloAceptarFalla(CargadorDoble):
            def _cargar(self, ruta):
                self.pedidas.append(ruta)
                return None if "accept" in ruta else SonidoDoble()

            loadSfx = _cargar
            loadMusic = _cargar

        cargador = SoloAceptarFalla()
        sonido = Audio(cargador)

        sonido.play_accept()
        sonido.play_back()

        assert sonido._sfx["back"].reproducido == 1
        assert "accept" not in sonido._sfx

    def test_a_sound_panda_marks_as_bad_is_not_kept(self, carpeta):
        """
        `loadSfx` no lanza con un fichero roto: devuelve un sonido en estado
        BAD, que reventaría más tarde y lejos de aquí.
        """
        from panda3d.core import AudioSound

        _crear(carpeta, "accept.wav")
        sonido = Audio(CargadorDoble(resultado=SonidoDoble(estado=AudioSound.BAD)))

        assert sonido._sfx == {}


class TestQueFicheroSeCoge:
    def test_both_extensions_are_tried(self, carpeta):
        """Poner un .ogg donde el README dice .wav tiene que funcionar."""
        _crear(carpeta, "accept.ogg")
        cargador = CargadorDoble()

        Audio(cargador)

        assert any(ruta.endswith("accept.ogg") for ruta in cargador.pedidas)

    def test_the_music_loops(self, carpeta):
        _crear(carpeta, "music.ogg")
        sonido = Audio(CargadorDoble())

        assert sonido._music.en_bucle is True


class TestElFrenoDelClicDeMover:
    """
    El detalle que decide si esto se puede usar. El carrusel acelera hasta
    unos veinte pasos por segundo mientras se mantiene la dirección, y un
    clic por paso deja de ser un sonido de interfaz.
    """

    def _con_reloj(self, carpeta):
        _crear(carpeta, "move.wav")
        self.ahora = 0.0
        return Audio(CargadorDoble(), clock=lambda: self.ahora)

    def test_two_in_a_row_only_sound_once(self, carpeta):
        sonido = self._con_reloj(carpeta)

        sonido.play_move()
        self.ahora += audio.MOVE_MIN_INTERVAL / 2
        sonido.play_move()

        assert sonido._sfx["move"].reproducido == 1

    def test_once_the_margin_passes_it_sounds_again(self, carpeta):
        sonido = self._con_reloj(carpeta)

        sonido.play_move()
        self.ahora += audio.MOVE_MIN_INTERVAL * 1.1
        sonido.play_move()

        assert sonido._sfx["move"].reproducido == 2

    def test_the_other_effects_have_no_brake(self, carpeta):
        """Pulsar dos veces seguidas tiene que sonar dos veces."""
        _crear(carpeta, "accept.wav")
        sonido = Audio(CargadorDoble())

        sonido.play_accept()
        sonido.play_accept()

        assert sonido._sfx["accept"].reproducido == 2


class TestVolumen:
    def test_it_goes_to_each_manager_as_a_fraction(self, carpeta):
        musica, efectos = ManagerDoble(), ManagerDoble()
        Audio(
            CargadorDoble(), sfx_manager=efectos, music_manager=musica,
        ).set_volumes(music=50, sfx=70)

        assert musica.volumen == 0.5
        assert efectos.volumen == 0.7

    def test_zero_music_actually_stops_it(self, carpeta):
        """
        Y no la deja sonando en silencio: descodificar para nada gasta
        batería en un Deck, y quien la pone a cero la está apagando.
        """
        _crear(carpeta, "music.ogg")
        sonido = Audio(CargadorDoble(), music_manager=ManagerDoble())
        sonido.start_music(50)

        sonido.set_volumes(music=0, sfx=70)

        assert sonido._music.parado == 1

    def test_starting_with_the_music_muted_does_not_play_it(self, carpeta):
        _crear(carpeta, "music.ogg")
        sonido = Audio(CargadorDoble(), music_manager=ManagerDoble())

        sonido.start_music(0)

        assert sonido._music.reproducido == 0

    def test_a_volume_out_of_range_is_clamped(self, carpeta):
        manager = ManagerDoble()
        Audio(CargadorDoble(), sfx_manager=manager).set_volumes(
            music=0, sfx=500,
        )

        assert manager.volumen == 1.0


class TestUnBotonUnSonido:
    """
    Hay acciones que aplican y cierran el menú de una vez —elegir un sistema
    de puntuación, Guardar, decir que sí a una confirmación—: pasan por
    "aceptar" y acto seguido por "volver", desde `_pop_menu`. Sonaban los dos
    clics pisándose en la misma pulsación.
    """

    def _con_reloj(self, carpeta):
        _crear(carpeta, "accept.wav", "back.wav")
        self.ahora = 0.0
        return Audio(CargadorDoble(), clock=lambda: self.ahora)

    def test_closing_right_after_accepting_does_not_click_twice(self, carpeta):
        sonido = self._con_reloj(carpeta)

        sonido.play_accept()
        sonido.play_back()

        assert sonido._sfx["accept"].reproducido == 1
        assert sonido._sfx["back"].reproducido == 0

    def test_going_back_on_its_own_does_sound(self, carpeta):
        sonido = self._con_reloj(carpeta)

        sonido.play_back()

        assert sonido._sfx["back"].reproducido == 1

    def test_a_deliberate_b_after_an_a_still_sounds(self, carpeta):
        """Entrar en un menú y salir de él son dos gestos, y suenan dos."""
        sonido = self._con_reloj(carpeta)

        sonido.play_accept()
        self.ahora += audio.BACK_AFTER_ACCEPT * 2
        sonido.play_back()

        assert sonido._sfx["back"].reproducido == 1
