"""
Leer el portapapeles del sistema.

Ninguna prueba toca el portapapeles de verdad ni ejecuta nada: se sustituye
`subprocess.run`. Lo que se comprueba es la política —en qué orden se
pregunta, qué se considera "no está instalado" y cómo se desmonta cada
formato—, no las herramientas, que son del sistema.
"""
import subprocess

import pytest

from puntueitor.core.services import clipboard
from puntueitor.core.services.clipboard import normalize, read_clipboard


class Respuesta:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


class RunDoble:
    """
    Un `subprocess.run` de mentira.

    `respuestas` mapea el nombre del binario a lo que contesta, o a una
    excepción que lanzar. Lo que no esté en el mapa se comporta como un
    binario que no está instalado.
    """

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.intentos = []

    def __call__(self, comando, **kwargs):
        binario = comando[0]
        self.intentos.append(binario)

        if binario not in self.respuestas:
            raise FileNotFoundError(binario)

        respuesta = self.respuestas[binario]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


@pytest.fixture
def run(monkeypatch):
    def montar(respuestas):
        doble = RunDoble(respuestas)
        monkeypatch.setattr(subprocess, "run", doble)
        return doble
    return montar


class TestOrden:
    def test_the_dedicated_tool_wins(self, run):
        """
        `wl-paste` antes que Klipper: si está, es la respuesta correcta sea
        cual sea el escritorio.
        """
        doble = run({
            "wl-paste": Respuesta("de wl-paste"),
            "qdbus6": Respuesta("de klipper"),
        })

        assert read_clipboard() == ("de wl-paste", "")
        assert doble.intentos == ["wl-paste"]

    def test_what_is_not_installed_is_skipped_quietly(self, run):
        """El caso NORMAL: se prueban varias porque no se sabe cuál habrá."""
        doble = run({"qdbus6": Respuesta("de klipper")})

        assert read_clipboard() == ("de klipper", "")
        assert doble.intentos == ["wl-paste", "xclip", "xsel", "qdbus6"]

    def test_it_falls_through_to_the_last_one(self, run):
        run({"gdbus": Respuesta("('de gdbus',)")})

        assert read_clipboard() == ("de gdbus", "")

    def test_with_nothing_at_all_it_explains_itself(self, run):
        """
        El modo juego del Deck: ni Klipper ni wl-paste. No se disimula.
        """
        run({})

        texto, motivo = read_clipboard()
        assert texto == ""
        assert "portapapeles" in motivo


class TestFallos:
    def test_a_tool_that_answers_with_an_error_is_not_a_failure(self, run):
        """
        `qdbus6` existe en cualquier equipo con Qt, pero contesta con error
        si no hay Klipper detrás. Hay que seguir probando.
        """
        doble = run({
            "qdbus6": Respuesta(returncode=1, stderr="no such service"),
            "gdbus": Respuesta("('el bueno',)"),
        })

        assert read_clipboard() == ("el bueno", "")
        assert "gdbus" in doble.intentos

    def test_a_timeout_does_not_propagate(self, run):
        run({
            "wl-paste": subprocess.TimeoutExpired("wl-paste", 3),
            "qdbus6": Respuesta("el bueno"),
        })

        assert read_clipboard() == ("el bueno", "")

    def test_an_os_error_does_not_propagate(self, run):
        run({
            "wl-paste": PermissionError("no se puede ejecutar"),
            "qdbus6": Respuesta("el bueno"),
        })

        assert read_clipboard() == ("el bueno", "")

    def test_it_never_raises(self, run):
        """
        Lo llama la interfaz, a veces desde un hilo: una excepción cruzando
        esa frontera es un cierre en seco. Da igual lo raro que sea el fallo
        de la herramienta del sistema.
        """
        run({
            "wl-paste": RuntimeError("cualquier cosa"),
            "qdbus6": Respuesta("el bueno"),
        })

        assert read_clipboard() == ("el bueno", "")

    def test_if_everything_explodes_it_still_returns(self, run):
        run({nombre: RuntimeError("boom") for nombre in
             ("wl-paste", "xclip", "xsel", "qdbus6", "qdbus", "gdbus")})

        texto, motivo = read_clipboard()
        assert texto == ""
        assert motivo

    def test_an_empty_clipboard_is_not_a_broken_clipboard(self, run):
        """
        Se distingue, y no se sigue preguntando: la vía funciona, es que no
        hay nada copiado. Otra vía devolvería algo más viejo.
        """
        doble = run({"wl-paste": Respuesta(""), "qdbus6": Respuesta("viejo")})

        texto, motivo = read_clipboard()
        assert texto == ""
        assert "vacío" in motivo
        assert doble.intentos == ["wl-paste"]


class TestGVariant:
    """`gdbus` no devuelve el texto pelado, sino `('texto',)`."""

    @pytest.mark.parametrize("salida,esperado", [
        ("('hola',)", "hola"),
        ('(\'con "comillas"\',)', 'con "comillas"'),
        ("('con \\'apóstrofo\\'',)", "con 'apóstrofo'"),
        ("('https://x/?a=1&b=2',)", "https://x/?a=1&b=2"),
    ])
    def test_it_unwraps(self, salida, esperado):
        assert clipboard._gvariant(salida) == esperado

    def test_something_that_is_not_a_tuple_does_not_raise(self):
        """El desmontaje de respaldo, por si la salida deja de parecerse."""
        assert clipboard._gvariant("('sin cerrar") == "sin cerrar"

    def test_an_escaped_newline_survives_the_unwrapping(self):
        """Lo quita `normalize` después, no esto."""
        assert clipboard._gvariant("('a\\nb',)") == "a\nb"


class TestNormalize:
    def test_the_trailing_newline_goes_away(self):
        """
        Una URL copiada del navegador suele traerlo, y dentro de un campo de
        una línea no se ve —pero viaja al canjear el código y la tienda lo
        rechaza sin que se entienda por qué.
        """
        assert normalize("https://x/?code=ABC\n") == "https://x/?code=ABC"

    def test_newlines_in_the_middle_too(self):
        assert normalize("https://x/\n?code=ABC") == "https://x/ ?code=ABC"

    def test_the_edges_are_trimmed(self):
        assert normalize("   ABC   ") == "ABC"

    def test_nothing_is_nothing(self):
        assert normalize("") == ""
        assert normalize(None) == ""
