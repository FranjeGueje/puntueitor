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
#
# Subido de 0.5 a 0.6 tras probarlo: con el umbral bajo, el stick empezaba a
# mover el carrusel antes de que se notara haberlo movido, y un stick con
# holgura (los mandos usados la cogen) podía navegar solo.
STICK_THRESHOLD = 0.6

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

#: Los cuatro lados de la cruceta que se siguen por eventos de pulsar/soltar.
_DPAD_SIDES = ("left", "right", "up", "down")

# Los gatillos (L2/R2) de un mando tipo Xbox NO son botones: son ejes
# analógicos (`Axis.left_trigger`), y Panda3D ni siquiera declara conocido su
# botón equivalente — comprobado en el Xbox Elite 2, donde
# `find_button(GamepadButton.ltrigger())` no devuelve nada utilizable. Así que
# hay que sondear el eje y detectar el flanco a mano.
#
# Dos umbrales en vez de uno para dar histéresis: con uno solo, un gatillo
# que se quede rozando el umbral (los analógicos no vuelven siempre a 0 clavado)
# dispararía el conmutador una y otra vez. Hay que soltarlo por debajo de
# RELEASE antes de que vuelva a contar como pulsado.
TRIGGER_PRESS_THRESHOLD = 0.6
TRIGGER_RELEASE_THRESHOLD = 0.35

# El stick DERECHO (el del Editor Rápido) necesita la misma histéresis que
# los gatillos, y por la misma razón, pero aquí se nota mucho más: cada
# empujón ESCRIBE en la base de datos.
#
# Con un solo umbral, un stick que se queda rozándolo —o que al soltarlo
# rebota y vuelve a pasar por él— dispara el gesto varias veces seguidas. Se
# vio en un mando de Xbox 360: un solo empujón dejaba en el log
# "backlog = True / False / True / False", o sea el estado marcado y
# desmarcado sin tocar nada más.
#
# El de pulsar va ALTO (hay que echar el stick a conciencia) y el de soltar
# BAJO (hay que devolverlo casi al centro antes de que cuente otro).
RSTICK_PRESS_THRESHOLD = 0.7
RSTICK_RELEASE_THRESHOLD = 0.3


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
        on_options: Callable[[], None] | None = None,
        on_scoring: Callable[[], None] | None = None,
        on_filter: Callable[[], None] | None = None,
        on_labels: Callable[[], None] | None = None,
        on_hidden: Callable[[], None] | None = None,
        on_refresh: Callable[[], None] | None = None,
        on_jump_start: Callable[[], None] | None = None,
        on_editor: Callable[[], None] | None = None,
        on_jump: Callable[[int], None] | None = None,
    ):
        super().__init__()
        self._app = app
        self._callbacks = {
            "confirm": on_confirm,
            "back": on_back,
            "options": on_options,
            "scoring": on_scoring,
            "filter": on_filter,
            "labels": on_labels,
            "hidden": on_hidden,
            "refresh": on_refresh,
            "jump_start": on_jump_start,
            "editor": on_editor,
        }
        # Aparte del resto: lleva argumento (hacia dónde saltar), así que no
        # encaja en el diccionario de gestos sin parámetros de `_fire`.
        self._on_jump = on_jump
        # Un flanco por gatillo, ver `update`.
        self._triggers_held = {"hidden": False, "refresh": False}
        # Empujón del stick derecho ya contado, hasta que vuelva al centro
        # (ver `right_stick`).
        self._rstick_held: tuple[int, int] = (0, 0)

        self._device_manager = InputDeviceManager.get_global_ptr()
        self._device: InputDevice | None = None
        self._dpad_held = dict.fromkeys(_DPAD_SIDES, False)
        self._hat_axis: int | None = None
        self._hat_axis_v: int | None = None

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
    def _find_hat_axes(device: InputDevice) -> tuple[int | None, int | None]:
        """
        Índices de los ejes horizontal y vertical de la cruceta, o None.

        Se buscan los DOS PRIMEROS ejes sin mapear (`Axis.none`): evdev
        numera ABS_HAT0X (0x10) antes que ABS_HAT0Y (0x11) y Panda3D los
        recorre en ese orden, así que el primero sin nombre es el horizontal
        y el segundo el vertical. Es una heurística, pero acotada — solo se
        miran los ejes que Panda3D ya ha declarado desconocidos, nunca los
        que sí tienen nombre.
        """
        unmapped = [
            index for index, axis in enumerate(device.axes)
            if axis.axis == InputDevice.Axis.none
        ]
        horizontal = unmapped[0] if len(unmapped) > 0 else None
        vertical = unmapped[1] if len(unmapped) > 1 else None
        return horizontal, vertical

    def _attach(self, device: InputDevice) -> None:
        self._device = device
        self._hat_axis, self._hat_axis_v = self._find_hat_axes(device)
        if self._hat_axis is None:
            logger.debug("gui3d: el mando no expone eje de cruceta sin mapear")
        # Si se soltó la cruceta con el mando ya desconectado, su evento de
        # "soltar" no llegó nunca y el estado se habría quedado pulsado para
        # siempre, con el carrusel corriendo solo.
        self._dpad_held = dict.fromkeys(_DPAD_SIDES, False)
        self._rstick_held = (0, 0)
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
            "face_x": "filter",
            "face_y": "labels",
            "start": "scoring",
            # "Select" en los mandos antiguos, "Back"/"View" en los de Xbox
            # modernos: es el mismo botón y Panda3D lo llama siempre `back`.
            # Ojo con el nombre: no tiene NADA que ver con el gesto "back"
            # de volver atrás, que es el botón B.
            "back": "options",
            # L3, el clic del stick izquierdo: al principio del carrusel. Es
            # un botón normal y llega como evento, al contrario que los
            # gatillos (ver `update`).
            "lstick": "jump_start",
            # R3: entra y sale del Editor Rápido.
            "rstick": "editor",
        }
        for button, gesture in bindings.items():
            self.accept(f"{EVENT_PREFIX}-{button}", self._fire, [gesture])

        # L1/R1: salto rápido de grupo. Estos SÍ son botones de verdad (a
        # diferencia de los gatillos, ver `update`), así que llegan como
        # eventos y no hay que sondear nada.
        self.accept(f"{EVENT_PREFIX}-lshoulder", self._fire_jump, [-1])
        self.accept(f"{EVENT_PREFIX}-rshoulder", self._fire_jump, [1])

        # La cruceta se sigue por eventos de pulsar/soltar además de por
        # sondeo (ver `direction`). `ButtonThrower` emite "<prefijo>-<botón>"
        # al pulsar y "<prefijo>-<botón>-up" al soltar, así que con los dos
        # se reconstruye el estado de "mantenido" sin depender de que el
        # dispositivo mantenga al día su ButtonState.
        for side in _DPAD_SIDES:
            button = f"dpad_{side}"
            self.accept(f"{EVENT_PREFIX}-{button}", self._set_dpad, [side, True])
            self.accept(f"{EVENT_PREFIX}-{button}-up", self._set_dpad, [side, False])

    def _set_dpad(self, side: str, held: bool) -> None:
        self._dpad_held[side] = held
        logger.debug(f"gui3d: cruceta {side} {'pulsada' if held else 'soltada'}")

    def _fire(self, gesture: str) -> None:
        callback = self._callbacks.get(gesture)
        if callback:
            callback()

    def _fire_jump(self, direction: int) -> None:
        if self._on_jump:
            self._on_jump(direction)

    # ──────────────────────────────
    # Dirección (estado continuo, por sondeo)
    # ──────────────────────────────

    def _button_pressed(self, button) -> bool:
        state = self._device.find_button(button)
        return bool(state and state.known and state.pressed)

    def _axis_direction(
        self,
        negative_side: str, positive_side: str,
        negative_button, positive_button,
        hat_axis: int | None,
        stick_axis,
        invert_hat: bool = False,
    ) -> int:
        """
        Un eje de dirección, combinando cruceta y stick. Ver `direction`.

        `invert_hat` está para el eje vertical: el hat da +1 hacia ABAJO
        (evdev cuenta la Y hacia abajo, como una pantalla), mientras que el
        stick da +1 hacia ARRIBA. Sin invertir uno de los dos, la cruceta y
        el stick moverían el menú en sentidos contrarios.
        """
        negative = self._dpad_held[negative_side] or self._button_pressed(negative_button)
        positive = self._dpad_held[positive_side] or self._button_pressed(positive_button)

        if hat_axis is not None:
            hat = self._device.axes[hat_axis].value
            if invert_hat:
                hat = -hat
            negative = negative or hat <= -HAT_THRESHOLD
            positive = positive or hat >= HAT_THRESHOLD

        axis = self._device.find_axis(stick_axis)
        value = axis.value if axis else 0.0
        negative = negative or value <= -STICK_THRESHOLD
        positive = positive or value >= STICK_THRESHOLD

        return (1 if positive else 0) - (1 if negative else 0)

    def direction(self) -> int:
        """
        Hacia dónde se está pidiendo ir en HORIZONTAL: -1, 0 o +1.

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
        return self._axis_direction(
            "left", "right",
            GamepadButton.dpad_left(), GamepadButton.dpad_right(),
            self._hat_axis, InputDevice.Axis.left_x,
        )

    def direction_v(self) -> int:
        """
        Lo mismo en VERTICAL, para navegar los menús: -1 arriba, +1 abajo.

        El signo va como en pantalla (+1 baja), no como en el mundo 3D,
        porque quien lo consume es una lista de menú que se recorre de
        arriba abajo.
        """
        if self._device is None:
            return 0
        # `_axis_direction` trabaja en la convención del mando (+1 = arriba,
        # que es como da los valores el stick); el menos de delante es lo
        # único que la pasa a la de pantalla (+1 = abajo).
        return -self._axis_direction(
            "down", "up",
            GamepadButton.dpad_down(), GamepadButton.dpad_up(),
            self._hat_axis_v, InputDevice.Axis.left_y,
            invert_hat=True,
        )

    def right_stick(self) -> tuple[int, int]:
        """
        Hacia dónde está echado el stick DERECHO: (x, y) de -1 a 1.

        En la convención de pantalla, +1 a la derecha y +1 hacia ABAJO, que es
        la que espera quien lo consume (la tabla del Editor Rápido).

        **Un solo eje a la vez**: con el stick en diagonal gana el que más se
        haya movido, y si empatan no se devuelve nada. Marcar dos estados de
        una sacudida es exactamente lo que haría desconfiar de un modo en el
        que cada empujón escribe en la base de datos.

        **Con histéresis** (ver `RSTICK_PRESS_THRESHOLD`): una vez contado un
        empujón, hay que devolver el stick casi al centro para que cuente el
        siguiente. Sin eso, un solo empujón marcaba y desmarcaba el estado
        varias veces, que es como se comportaba de verdad en un mando.

        Es ESTADO, como `direction()`: quien lo use tiene que detectar el
        flanco por su cuenta si no quiere repetición.
        """
        if self._device is None:
            self._rstick_held = (0, 0)
            return (0, 0)

        eje_x = self._device.find_axis(InputDevice.Axis.right_x)
        eje_y = self._device.find_axis(InputDevice.Axis.right_y)
        x = eje_x.value if eje_x else 0.0
        # El stick da +1 hacia arriba; aquí se cuenta al revés.
        y = -eje_y.value if eje_y else 0.0

        if self._rstick_held != (0, 0):
            # Ya hay un empujón contado: solo se suelta cuando el stick ha
            # vuelto casi al centro EN LOS DOS EJES. Mientras tanto se sigue
            # devolviendo lo mismo, así que quien mire el flanco no ve nada.
            if max(abs(x), abs(y)) <= RSTICK_RELEASE_THRESHOLD:
                self._rstick_held = (0, 0)
            return self._rstick_held

        if max(abs(x), abs(y)) < RSTICK_PRESS_THRESHOLD:
            return (0, 0)
        if abs(x) == abs(y):
            return (0, 0)
        if abs(x) > abs(y):
            self._rstick_held = (1 if x > 0 else -1, 0)
        else:
            self._rstick_held = (0, 1 if y > 0 else -1)
        return self._rstick_held

    def update(self) -> None:
        """
        Sondea lo que no llega como evento. Llamar una vez por frame.

        Los dos gatillos: son ejes analógicos y por tanto no disparan
        eventos de botón. L2 conmuta los juegos ocultos y R2 actualiza la
        biblioteca.
        """
        if self._device is None:
            return

        self._poll_trigger(InputDevice.Axis.left_trigger, "hidden")
        self._poll_trigger(InputDevice.Axis.right_trigger, "refresh")

    def _poll_trigger(self, axis_id, gesture: str) -> None:
        """
        Convierte un gatillo en un gesto de "recién pulsado".

        Con histéresis (dos umbrales) y no con uno solo: los gatillos no
        vuelven a cero limpiamente, y con un único umbral el temblor
        alrededor de él dispararía el gesto varias veces por pulsación. Y
        solo en el FLANCO: sin eso, mantener el gatillo un segundo lo
        dispararía sesenta veces.
        """
        axis = self._device.find_axis(axis_id)
        if axis is None:
            return

        value = axis.value
        if self._triggers_held[gesture]:
            if value <= TRIGGER_RELEASE_THRESHOLD:
                self._triggers_held[gesture] = False
        elif value >= TRIGGER_PRESS_THRESHOLD:
            self._triggers_held[gesture] = True
            self._fire(gesture)

    def destroy(self) -> None:
        self.ignore_all()
