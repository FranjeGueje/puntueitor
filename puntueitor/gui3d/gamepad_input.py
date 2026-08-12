"""
Soporte de mando (gamepad) para el frontend 3D, con hot-plug.

Panda3D expone los mandos vía `InputDeviceManager`; una vez "adjuntado" con
`attach_input_device`, sus botones se propagan como eventos normales del
messenger (p.ej. "gamepad-face_a"), pero los ejes analógicos (stick) no —
esos hay que sondearlos cada frame. Este módulo hace ambas cosas y expone
confirmar, volver y abrir el menú de opciones como eventos, y la dirección
(cruceta o stick) como ESTADO consultable con `direction()`, para que quien
navega pueda repetir mientras se mantenga pulsado.
"""
import logging
from collections.abc import Callable

from direct.showbase.DirectObject import DirectObject
from panda3d.core import GamepadButton, InputDevice, InputDeviceManager

logger = logging.getLogger(__name__)

EVENT_PREFIX = "gamepad"

# A partir de cuánto cuenta que el stick está echado a un lado. No hay
# histéresis ni "hay que volver al centro": esto devuelve el ESTADO actual y
# quien navega (`app.App._update_navigation`) se encarga del ritmo de
# repetición. Antes se detectaba el flanco aquí y había que soltar el stick
# para volver a moverse, que era justo lo que impedía recorrer el carrusel
# dejándolo echado.
STICK_THRESHOLD = 0.5

# La cruceta de muchos mandos (Xbox entre ellos) NO llega como botones: el
# kernel la expone como el eje "hat" ABS_HAT0X/ABS_HAT0Y, y Panda3D no lo
# mapea a ningún `Axis` con nombre — aparece como `Axis.none`. Y como el
# dispositivo SÍ se declara gamepad, Panda3D anuncia los botones `dpad_*`
# como existentes (`find_button(...).known` es True) aunque no se disparen
# jamás. Esa combinación es una trampa perfecta: parece que la cruceta está
# soportada, y nunca hace nada. Comprobado en un Xbox Elite 2: el kernel lo
# confirma en `/proc/bus/input/devices` con `B: ABS=3003f`, cuyos bits 16 y
# 17 son justamente HAT0X y HAT0Y.
#
# El hat es digital (-1, 0, +1), así que un umbral alto basta y evita
# confundirlo con un eje analógico si el orden no fuera el esperado.
HAT_THRESHOLD = 0.5


class GamepadInput(DirectObject):
    """
    Escucha el primer mando conectado: gestos puntuales a callbacks, y la
    dirección disponible como estado.

    Todos los callbacks son opcionales; se ignoran los gestos sin callback.
    """

    def __init__(
        self,
        app,
        on_confirm: Callable[[], None] | None = None,
        on_back: Callable[[], None] | None = None,
        on_menu: Callable[[], None] | None = None,
        on_labels: Callable[[], None] | None = None,
    ):
        super().__init__()
        self._app = app
        self._callbacks = {
            "confirm": on_confirm,
            "back": on_back,
            "menu": on_menu,
            "labels": on_labels,
        }

        self._device_manager = InputDeviceManager.get_global_ptr()
        self._device: InputDevice | None = None
        self._dpad_held = {"left": False, "right": False}

        self.accept("connect-device", self._on_device_connected)
        self.accept("disconnect-device", self._on_device_disconnected)

        self._attach_first_available()

    # ──────────────────────────────
    # Conexión / desconexión
    # ──────────────────────────────

    def _attach_first_available(self) -> None:
        gamepads = self._device_manager.get_devices(InputDevice.DeviceClass.gamepad)
        if gamepads:
            self._attach(gamepads[0])
        else:
            logger.info("gui3d: no hay mando conectado; solo teclado")

    @staticmethod
    def _find_hat_axis(device: InputDevice) -> int | None:
        """
        Índice del eje horizontal de la cruceta, o None si no lo hay.

        Se busca el PRIMER eje sin mapear (`Axis.none`): evdev numera
        ABS_HAT0X (0x10) antes que ABS_HAT0Y (0x11) y Panda3D los recorre en
        ese orden, así que el primero sin nombre es el horizontal. Es una
        heurística, pero acotada — solo se miran los ejes que Panda3D ya ha
        declarado desconocidos, nunca los que sí tienen nombre.
        """
        for index, axis in enumerate(device.axes):
            if axis.axis == InputDevice.Axis.none:
                return index
        return None

    def _attach(self, device: InputDevice) -> None:
        self._device = device
        self._hat_axis = self._find_hat_axis(device)
        if self._hat_axis is None:
            logger.debug("gui3d: el mando no expone eje de cruceta sin mapear")
        # Si se soltó la cruceta con el mando ya desconectado, su evento de
        # "soltar" no llegó nunca y el estado se habría quedado pulsado para
        # siempre, con el carrusel corriendo solo.
        self._dpad_held = {"left": False, "right": False}
        self._app.attach_input_device(device, prefix=EVENT_PREFIX)
        self._bind_buttons()
        logger.info(f"gui3d: mando conectado: {device.name}")

    def _on_device_connected(self, device: InputDevice) -> None:
        if self._device is None and device.device_class == InputDevice.DeviceClass.gamepad:
            self._attach(device)

    def _on_device_disconnected(self, device: InputDevice) -> None:
        if self._device is device:
            logger.info(f"gui3d: mando desconectado: {device.name}")
            self._app.detach_input_device(device)
            self._device = None
            self._attach_first_available()

    # ──────────────────────────────
    # Botones (discretos, vía messenger)
    # ──────────────────────────────

    def _bind_buttons(self) -> None:
        bindings = {
            "face_a": "confirm",
            "face_b": "back",
            "face_y": "labels",
            "start": "menu",
        }
        for button, gesture in bindings.items():
            self.accept(f"{EVENT_PREFIX}-{button}", self._fire, [gesture])

        # La cruceta se sigue por eventos de pulsar/soltar además de por
        # sondeo (ver `direction`). `ButtonThrower` emite "<prefijo>-<botón>"
        # al pulsar y "<prefijo>-<botón>-up" al soltar, así que con los dos
        # se reconstruye el estado de "mantenido" sin depender de que el
        # dispositivo mantenga al día su ButtonState.
        for button, side in (("dpad_left", "left"), ("dpad_right", "right")):
            self.accept(f"{EVENT_PREFIX}-{button}", self._set_dpad, [side, True])
            self.accept(f"{EVENT_PREFIX}-{button}-up", self._set_dpad, [side, False])

    def _set_dpad(self, side: str, held: bool) -> None:
        self._dpad_held[side] = held
        logger.debug(f"gui3d: cruceta {side} {'pulsada' if held else 'soltada'}")

    def _fire(self, gesture: str) -> None:
        callback = self._callbacks.get(gesture)
        if callback:
            callback()

    # ──────────────────────────────
    # Dirección (estado continuo, por sondeo)
    # ──────────────────────────────

    def _button_pressed(self, button) -> bool:
        state = self._device.find_button(button)
        return bool(state and state.known and state.pressed)

    def direction(self) -> int:
        """
        Hacia dónde se está pidiendo ir AHORA MISMO: -1, 0 o +1.

        Vale tanto la cruceta como el stick izquierdo, indistintamente, y
        cuenta mientras se mantengan — no es un flanco. Si se pulsan los dos
        lados a la vez se anulan, que es menos molesto que elegir uno.

        La cruceta se mira por TRES vías y basta con que una diga que sí:
        el eje "hat" sin mapear (ver `HAT_THRESHOLD`, que es la que funciona
        en los mandos tipo Xbox), el estado reconstruido de sus eventos de
        pulsar/soltar, y el `ButtonState` del dispositivo. No es redundancia
        gratuita: cada una funciona en un tipo de mando distinto y ninguna
        sirve para todos.
        """
        if self._device is None:
            return 0

        left = self._dpad_held["left"] or self._button_pressed(GamepadButton.dpad_left())
        right = self._dpad_held["right"] or self._button_pressed(GamepadButton.dpad_right())

        if self._hat_axis is not None:
            hat = self._device.axes[self._hat_axis].value
            left = left or hat <= -HAT_THRESHOLD
            right = right or hat >= HAT_THRESHOLD

        axis = self._device.find_axis(InputDevice.Axis.left_x)
        value = axis.value if axis else 0.0
        left = left or value <= -STICK_THRESHOLD
        right = right or value >= STICK_THRESHOLD

        return (1 if right else 0) - (1 if left else 0)

    def destroy(self) -> None:
        self.ignore_all()
