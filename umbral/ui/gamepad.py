from __future__ import annotations

import ctypes
import os
import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

# XInput button masks
XINPUT_DPAD_UP = 0x0001
XINPUT_DPAD_DOWN = 0x0002
XINPUT_DPAD_LEFT = 0x0004
XINPUT_DPAD_RIGHT = 0x0008
XINPUT_START = 0x0010
XINPUT_BACK = 0x0020
XINPUT_LEFT_SHOULDER = 0x0100
XINPUT_RIGHT_SHOULDER = 0x0200
XINPUT_A = 0x1000
XINPUT_B = 0x2000
XINPUT_X = 0x4000
XINPUT_Y = 0x8000

STICK_DEADZONE = 9500


class _XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_ulong),
        ("Gamepad", _XINPUT_GAMEPAD),
    ]


def _load_xinput():
    if os.name != "nt":
        return None
    for dll in ("xinput1_4.dll", "xinput9_1_0.dll", "xinput1_3.dll"):
        try:
            lib = ctypes.windll.LoadLibrary(dll)
            fn = lib.XInputGetState
            fn.argtypes = [ctypes.c_ulong, ctypes.POINTER(_XINPUT_STATE)]
            fn.restype = ctypes.c_ulong
            return fn
        except OSError:
            continue
    return None


class GamepadWatcher(QObject):
    """Lightweight XInput gamepad poller emitting high-level navigation actions."""

    navigate_left = Signal()
    navigate_right = Signal()
    navigate_up = Signal()
    navigate_down = Signal()
    confirm = Signal()
    back = Signal()
    flip_requested = Signal()
    favorite_requested = Signal()
    prev_system = Signal()
    next_system = Signal()
    fullscreen_requested = Signal()
    connected_changed = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._get_state = _load_xinput()
        self._connected = False
        self._prev_buttons = 0
        self._repeat_dir = ""
        self._repeat_next_at = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(24)
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        if self._get_state is not None and not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def is_connected(self) -> bool:
        return self._connected

    def _read_first_controller(self) -> Optional[_XINPUT_GAMEPAD]:
        if self._get_state is None:
            return None
        state = _XINPUT_STATE()
        for user_index in range(4):
            if self._get_state(user_index, ctypes.byref(state)) == 0:
                return state.Gamepad
        return None

    def _poll(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "isActiveWindow") and not parent.isActiveWindow():
            self._prev_buttons = 0
            self._repeat_dir = ""
            return

        pad = self._read_first_controller()
        now_connected = pad is not None
        if now_connected != self._connected:
            self._connected = now_connected
            self.connected_changed.emit(now_connected)
            self._timer.setInterval(24 if now_connected else 250)
        if pad is None:
            self._prev_buttons = 0
            self._repeat_dir = ""
            return

        buttons = int(pad.wButtons)
        pressed = buttons & ~self._prev_buttons
        self._prev_buttons = buttons

        if pressed & XINPUT_A:
            self.confirm.emit()
        if pressed & XINPUT_B:
            self.back.emit()
        if pressed & XINPUT_X:
            self.flip_requested.emit()
        if pressed & XINPUT_Y:
            self.favorite_requested.emit()
        if pressed & XINPUT_LEFT_SHOULDER:
            self.prev_system.emit()
        if pressed & XINPUT_RIGHT_SHOULDER:
            self.next_system.emit()
        if pressed & XINPUT_START:
            self.fullscreen_requested.emit()

        # D-Pad + Left Stick directional navigation with repeat
        direction = ""
        if (buttons & XINPUT_DPAD_LEFT) or pad.sThumbLX < -STICK_DEADZONE:
            direction = "left"
        elif (buttons & XINPUT_DPAD_RIGHT) or pad.sThumbLX > STICK_DEADZONE:
            direction = "right"
        elif (buttons & XINPUT_DPAD_UP) or pad.sThumbLY > STICK_DEADZONE:
            direction = "up"
        elif (buttons & XINPUT_DPAD_DOWN) or pad.sThumbLY < -STICK_DEADZONE:
            direction = "down"

        now = time.monotonic()
        if not direction:
            self._repeat_dir = ""
            return
        if direction != self._repeat_dir:
            self._repeat_dir = direction
            self._repeat_next_at = now + 0.34
            self._emit_direction(direction)
        elif now >= self._repeat_next_at:
            self._repeat_next_at = now + 0.13
            self._emit_direction(direction)

    def _emit_direction(self, direction: str) -> None:
        if direction == "left":
            self.navigate_left.emit()
        elif direction == "right":
            self.navigate_right.emit()
        elif direction == "up":
            self.navigate_up.emit()
        elif direction == "down":
            self.navigate_down.emit()
