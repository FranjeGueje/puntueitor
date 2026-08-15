"""
El stick derecho, que es el que escribe en la base de datos.

Se prueba `GamepadInput.right_stick` con un dispositivo de mentira, sin
Panda3D de por medio más allá del enum de ejes: lo que importa es la máquina
de estados de la histéresis, y esa es aritmética.

El caso que da nombre a todo esto está en `test_a_single_push_counts_once`:
con un solo umbral, un empujón real dejaba en el log el estado marcado y
desmarcado cuatro veces seguidas.
"""
import pytest

from puntueitor.gui3d.gamepad_input import (
    RSTICK_PRESS_THRESHOLD,
    RSTICK_RELEASE_THRESHOLD,
    GamepadInput,
)


class _Eje:
    def __init__(self):
        self.value = 0.0


class _Mando:
    """Lo único que `right_stick` le pide al dispositivo."""

    def __init__(self):
        self.x = _Eje()
        self.y = _Eje()

    def find_axis(self, axis_id):
        from panda3d.core import InputDevice
        return self.x if axis_id == InputDevice.Axis.right_x else self.y


@pytest.fixture
def mando(monkeypatch):
    """Un `GamepadInput` sin construir (no toca Panda3D) con su dispositivo."""
    entrada = GamepadInput.__new__(GamepadInput)
    entrada._device = _Mando()
    entrada._rstick_held = (0, 0)
    return entrada


def _empujar(mando, x=0.0, y=0.0):
    """Coloca el stick. `y` en convención de MANDO: +1 es arriba."""
    mando._device.x.value = x
    mando._device.y.value = y
    return mando.right_stick()


class TestDirecciones:
    def test_up_is_negative_y_on_screen(self, mando):
        """El stick da +1 arriba y aquí se cuenta como -1: es la pantalla."""
        assert _empujar(mando, y=1.0) == (0, -1)

    def test_down(self, mando):
        assert _empujar(mando, y=-1.0) == (0, 1)

    def test_right(self, mando):
        assert _empujar(mando, x=1.0) == (1, 0)

    def test_left(self, mando):
        assert _empujar(mando, x=-1.0) == (-1, 0)

    def test_centred(self, mando):
        assert _empujar(mando) == (0, 0)


class TestUnSoloEje:
    def test_a_diagonal_picks_the_dominant_axis(self, mando):
        """
        Nunca dos estados de una sacudida: nadie echa el stick perfectamente
        recto, y marcar "terminado" al ir a por "favorito" es de las cosas
        que hacen desconfiar de un modo así.
        """
        assert _empujar(mando, x=0.95, y=0.75) == (1, 0)

    def test_a_perfect_diagonal_does_nothing(self, mando):
        assert _empujar(mando, x=0.9, y=-0.9) == (0, 0)


class TestHisteresis:
    def test_a_soft_push_is_ignored(self, mando):
        """Hay que echar el stick a conciencia."""
        assert _empujar(mando, x=RSTICK_PRESS_THRESHOLD - 0.05) == (0, 0)

    def test_a_single_push_counts_once(self, mando):
        """
        EL BUG. Un empujón real no llega limpio: el eje sube, tiembla
        alrededor del umbral y al soltarlo rebota. Con un solo umbral, cada
        cruce contaba como un gesto nuevo, y en el log quedaba
        "backlog = True / False / True / False" de un solo empujón.

        Aquí se simula ese temblor y solo puede haber UN flanco.
        """
        # Sube, se suelta a medias, rebota y vuelve a caer, cruzando varias
        # veces el 0.5 del umbral único que había antes: con aquel salían
        # tres gestos de aquí.
        recorrido = [0.0, 0.45, 0.9, 0.4, 0.62, 0.35, 0.55, 0.32, 0.2, 0.05]
        lecturas = [_empujar(mando, x=v) for v in recorrido]

        flancos = sum(
            1 for antes, ahora in zip([(0, 0)] + lecturas, lecturas)
            if ahora != (0, 0) and antes == (0, 0)
        )
        assert flancos == 1

    def test_it_re_arms_only_near_the_centre(self, mando):
        _empujar(mando, x=1.0)
        # Todavía echado: sigue "pulsado", así que no hay flanco nuevo.
        assert _empujar(mando, x=RSTICK_RELEASE_THRESHOLD + 0.05) == (1, 0)
        # De vuelta al centro: se suelta.
        assert _empujar(mando, x=0.0) == (0, 0)
        # Y ahora sí cuenta otro.
        assert _empujar(mando, x=1.0) == (1, 0)

    def test_the_opposite_direction_needs_the_centre_first(self, mando):
        """
        Pasar de derecha a izquierda sin soltar no vale: el stick cruza el
        centro por el camino, y si contara al vuelo un barrido marcaría dos
        estados.
        """
        assert _empujar(mando, x=1.0) == (1, 0)
        assert _empujar(mando, x=-1.0) == (1, 0)  # sigue el anterior
        _empujar(mando, x=0.0)
        assert _empujar(mando, x=-1.0) == (-1, 0)

    def test_the_thresholds_are_not_the_same(self, mando):
        """Sin separación entre los dos no hay histéresis que valga."""
        assert RSTICK_RELEASE_THRESHOLD < RSTICK_PRESS_THRESHOLD

    def test_without_a_device(self):
        entrada = GamepadInput.__new__(GamepadInput)
        entrada._device = None
        entrada._rstick_held = (1, 0)
        assert entrada.right_stick() == (0, 0)
