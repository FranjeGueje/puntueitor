"""
Soporte de mando (gamepad) para el prototipo, con hot-plug.

Panda3D expone los mandos vía `InputDeviceManager`; una vez "adjuntado" con
`attach_input_device`, sus botones se propagan como eventos normales del
messenger (p.ej. "gamepad-face_a"), pero los ejes analógicos (stick) no —
esos hay que sondearlos cada frame. Este módulo hace ambas cosas y expone
solo los cinco gestos que necesita un menú: mover izquierda/derecha,
confirmar, volver y abrir el menú de opciones.
"""
import logging
from collections.abc import Callable

from direct.showbase.DirectObject import DirectObject
from panda3d.core import InputDevice, InputDeviceManager

logger = logging.getLogger(__name__)

EVENT_PREFIX = "gamepad"

# Umbral y "zona muerta" del stick: hay que superar el umbral para navegar, y
# volver a la zona muerta antes de que un nuevo movimiento cuente — si no, un
# stick al fondo dispararía movimiento en cada frame.
STICK_THRESHOLD = 0.5
STICK_DEADZONE = 0.2


class GamepadInput(DirectObject):
    """
    Escucha el primer mando conectado y traduce sus gestos a callbacks.

    Todos los callbacks son opcionales; se ignoran los gestos sin callback.
    """

    def __init__(
        self,
        app,
        on_left: Callable[[], None] | None = None,
        on_right: Callable[[], None] | None = None,
        on_confirm: Callable[[], None] | None = None,
        on_back: Callable[[], None] | None = None,
        on_menu: Callable[[], None] | None = None,
    ):
        super().__init__()
        self._app = app
        self._task_mgr = app.task_mgr
        self._callbacks = {
            "left": on_left,
            "right": on_right,
            "confirm": on_confirm,
            "back": on_back,
            "menu": on_menu,
        }

        self._device_manager = InputDeviceManager.get_global_ptr()
        self._device: InputDevice | None = None
        self._stick_neutral = True

        self.accept("connect-device", self._on_device_connected)
        self.accept("disconnect-device", self._on_device_disconnected)

        self._attach_first_available()
        self._task_mgr.add(self._poll_stick, "gamepad-poll-stick")

    # ──────────────────────────────
    # Conexión / desconexión
    # ──────────────────────────────

    def _attach_first_available(self) -> None:
        gamepads = self._device_manager.get_devices(InputDevice.DeviceClass.gamepad)
        if gamepads:
            self._attach(gamepads[0])
        else:
            logger.info("gui3d: no hay mando conectado; solo teclado")

    def _attach(self, device: InputDevice) -> None:
        self._device = device
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
            "dpad_left": "left",
            "dpad_right": "right",
            "face_a": "confirm",
            "face_b": "back",
            "start": "menu",
        }
        for button, gesture in bindings.items():
            self.accept(f"{EVENT_PREFIX}-{button}", self._fire, [gesture])

    def _fire(self, gesture: str) -> None:
        callback = self._callbacks.get(gesture)
        if callback:
            callback()

    # ──────────────────────────────
    # Stick analógico (continuo, por sondeo)
    # ──────────────────────────────

    def _poll_stick(self, task):
        if self._device is None:
            return task.cont

        axis = self._device.find_axis(InputDevice.Axis.left_x)
        value = axis.value if axis else 0.0

        if self._stick_neutral:
            if value >= STICK_THRESHOLD:
                self._fire("right")
                self._stick_neutral = False
            elif value <= -STICK_THRESHOLD:
                self._fire("left")
                self._stick_neutral = False
        elif abs(value) < STICK_DEADZONE:
            self._stick_neutral = True

        return task.cont

    def destroy(self) -> None:
        self._task_mgr.remove("gamepad-poll-stick")
        self.ignore_all()
