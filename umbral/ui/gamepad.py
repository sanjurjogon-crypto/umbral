from __future__ import annotations

import ctypes
from ctypes import wintypes
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

# Known USB/Bluetooth VID/PID controller names
_KNOWN_CONTROLLERS: dict[tuple[int, int], str] = {
    (0x054C, 0x0268): "Mando de PS3 (DualShock 3)",
    (0x054C, 0x05C4): "Mando de PS4 (DualShock 4)",
    (0x054C, 0x09CC): "Mando de PS4 (DualShock 4 v2)",
    (0x054C, 0x0BA0): "Adaptador DualShock 4",
    (0x054C, 0x0CE6): "Mando de PS5 (DualSense)",
    (0x054C, 0x0DF2): "Mando de PS5 (DualSense Edge)",
    (0x057E, 0x2009): "Mando de Nintendo Switch Pro",
    (0x057E, 0x2006): "Joy-Con (L)",
    (0x057E, 0x2007): "Joy-Con (R)",
    (0x045E, 0x028E): "Mando de Xbox 360",
    (0x045E, 0x028F): "Mando de Xbox 360 inalámbrico",
    (0x045E, 0x02D1): "Mando de Xbox One",
    (0x045E, 0x02DD): "Mando de Xbox One",
    (0x045E, 0x02E0): "Mando de Xbox One Bluetooth",
    (0x045E, 0x02EA): "Mando de Xbox One S",
    (0x045E, 0x0B12): "Mando de Xbox Series X|S",
    (0x045E, 0x0B13): "Mando de Xbox Series X|S Bluetooth",
}

_VENDOR_NAMES: dict[int, str] = {
    0x054C: "Mando PlayStation",
    0x045E: "Mando Xbox",
    0x057E: "Mando Nintendo",
    0x2DC8: "Mando 8BitDo",
    0x046D: "Mando Logitech",
}


def identify_controller(vid: int, pid: int, fallback: str = "") -> str:
    if (vid, pid) in _KNOWN_CONTROLLERS:
        return _KNOWN_CONTROLLERS[(vid, pid)]
    if vid in _VENDOR_NAMES:
        return _VENDOR_NAMES[vid]
    clean = (fallback or "").strip()
    if clean and "microsoft pc-joystick" not in clean.lower():
        return clean
    return "Mando"


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


class _JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("dwXpos", wintypes.DWORD),
        ("dwYpos", wintypes.DWORD),
        ("dwZpos", wintypes.DWORD),
        ("dwRpos", wintypes.DWORD),
        ("dwUpos", wintypes.DWORD),
        ("dwVpos", wintypes.DWORD),
        ("dwButtons", wintypes.DWORD),
        ("dwButtonNumber", wintypes.DWORD),
        ("dwPOV", wintypes.DWORD),
        ("dwReserved1", wintypes.DWORD),
        ("dwReserved2", wintypes.DWORD),
    ]


class _JOYCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("szPname", wintypes.WCHAR * 32),
        ("wXmin", wintypes.UINT),
        ("wXmax", wintypes.UINT),
        ("wYmin", wintypes.UINT),
        ("wYmax", wintypes.UINT),
        ("wZmin", wintypes.UINT),
        ("wZmax", wintypes.UINT),
        ("wNumButtons", wintypes.UINT),
        ("wPeriodMin", wintypes.UINT),
        ("wPeriodMax", wintypes.UINT),
        ("wRmin", wintypes.UINT),
        ("wRmax", wintypes.UINT),
        ("wUmin", wintypes.UINT),
        ("wUmax", wintypes.UINT),
        ("wVmin", wintypes.UINT),
        ("wVmax", wintypes.UINT),
        ("wCaps", wintypes.UINT),
        ("wMaxAxes", wintypes.UINT),
        ("wNumAxes", wintypes.UINT),
        ("wMaxButtons", wintypes.UINT),
        ("szRegKey", wintypes.WCHAR * 32),
        ("szOEMVxD", wintypes.WCHAR * 260),
    ]


class _RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [
        ("hDevice", wintypes.HANDLE),
        ("dwType", wintypes.DWORD),
    ]


class _RID_DEVICE_INFO_HID(ctypes.Structure):
    _fields_ = [
        ("dwVendorId", wintypes.DWORD),
        ("dwProductId", wintypes.DWORD),
        ("dwVersionNumber", wintypes.DWORD),
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
    ]


class _RID_DEVICE_INFO_UNION(ctypes.Union):
    _fields_ = [("hid", _RID_DEVICE_INFO_HID)]


class _RID_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("dwType", wintypes.DWORD),
        ("u", _RID_DEVICE_INFO_UNION),
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


def _load_winmm():
    if os.name != "nt":
        return None, None
    try:
        lib = ctypes.windll.LoadLibrary("winmm.dll")
        get_pos = lib.joyGetPosEx
        get_pos.argtypes = [wintypes.UINT, ctypes.POINTER(_JOYINFOEX)]
        get_pos.restype = wintypes.UINT
        get_caps = lib.joyGetDevCapsW
        get_caps.argtypes = [ctypes.c_size_t, ctypes.POINTER(_JOYCAPSW), wintypes.UINT]
        get_caps.restype = wintypes.UINT
        return get_pos, get_caps
    except (OSError, AttributeError):
        return None, None


def _detect_rawinput_gamepad() -> Optional[str]:
    """Detect any USB/Bluetooth HID Gamepad or Joystick (PS3/PS4/PS5/Xbox/Switch) via RawInput."""
    if os.name != "nt":
        return None
    try:
        user32 = ctypes.windll.user32
        count = wintypes.UINT(0)
        sz = ctypes.sizeof(_RAWINPUTDEVICELIST)
        if user32.GetRawInputDeviceList(None, ctypes.byref(count), sz) != 0 or count.value == 0:
            return None
        devices = (_RAWINPUTDEVICELIST * count.value)()
        if user32.GetRawInputDeviceList(devices, ctypes.byref(count), sz) == -1:
            return None
        for dev in devices[: count.value]:
            if dev.dwType != 2:  # RIM_TYPEHID
                continue
            info = _RID_DEVICE_INFO()
            info.cbSize = ctypes.sizeof(_RID_DEVICE_INFO)
            info_sz = wintypes.UINT(info.cbSize)
            # RIDI_DEVICEINFO = 0x2000000B
            res = user32.GetRawInputDeviceInfoW(
                dev.hDevice, 0x2000000B, ctypes.byref(info), ctypes.byref(info_sz)
            )
            if res == -1:
                continue
            hid = info.u.hid
            # Generic Desktop (0x01) -> Joystick (0x04) or Gamepad (0x05) or Multi-axis (0x08)
            if hid.usUsagePage == 0x01 and hid.usUsage in (0x04, 0x05, 0x08):
                return identify_controller(int(hid.dwVendorId), int(hid.dwProductId))
    except Exception:  # noqa: BLE001
        return None
    return None


class GamepadWatcher(QObject):
    """Unified Windows gamepad poller (XInput + DirectInput/winmm + RawInput HID for PS3/PS4/PS5/Xbox/Switch)."""

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
    device_changed = Signal(bool, str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._get_state = _load_xinput()
        self._joy_pos, self._joy_caps = _load_winmm()
        self._connected = False
        self._device_name = ""
        self._prev_buttons = 0
        self._repeat_dir = ""
        self._repeat_next_at = 0.0
        self._raw_check_at = 0.0
        self._raw_name: Optional[str] = None
        self._timer = QTimer(self)
        self._timer.setInterval(24)
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        if (
            self._get_state is not None or self._joy_pos is not None
        ) and not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def is_connected(self) -> bool:
        return self._connected

    def device_name(self) -> str:
        return self._device_name

    def _read_xinput(self) -> Optional[tuple[int, int, int, str]]:
        if self._get_state is None:
            return None
        state = _XINPUT_STATE()
        for user_index in range(4):
            if self._get_state(user_index, ctypes.byref(state)) == 0:
                g = state.Gamepad
                name = self._raw_name or "Mando de Xbox"
                return int(g.wButtons), int(g.sThumbLX), int(g.sThumbLY), name
        return None

    def _read_winmm(self) -> Optional[tuple[int, int, int, str]]:
        if self._joy_pos is None:
            return None
        info = _JOYINFOEX()
        info.dwSize = ctypes.sizeof(_JOYINFOEX)
        info.dwFlags = 0x000000FF  # JOY_RETURNALL
        for joy_id in range(16):
            if self._joy_pos(joy_id, ctypes.byref(info)) != 0:
                continue
            name = self._raw_name or "Mando"
            if self._joy_caps is not None:
                caps = _JOYCAPSW()
                if self._joy_caps(joy_id, ctypes.byref(caps), ctypes.sizeof(_JOYCAPSW)) == 0:
                    name = identify_controller(int(caps.wMid), int(caps.wPid), caps.szPname)
            raw_btn = int(info.dwButtons)
            # Map DirectInput / PlayStation / generic buttons -> XInput masks
            # PS4/PS5 HID: 1=Square(X), 2=Cross(A), 3=Circle(B), 4=Triangle(Y), 5=L1, 6=R1, 10=Options(Start)
            mapped = 0
            if raw_btn & (1 << 1) or raw_btn & (1 << 0):  # Cross / A
                mapped |= XINPUT_A if (raw_btn & (1 << 1)) else 0
            if raw_btn & (1 << 2):  # Circle / B
                mapped |= XINPUT_B
            if raw_btn & (1 << 0):  # Square / X (or Xbox A fallback handled below)
                mapped |= XINPUT_X
            if raw_btn & (1 << 3):  # Triangle / Y
                mapped |= XINPUT_Y
            if raw_btn & (1 << 4):
                mapped |= XINPUT_LEFT_SHOULDER
            if raw_btn & (1 << 5):
                mapped |= XINPUT_RIGHT_SHOULDER
            if raw_btn & (1 << 9) or raw_btn & (1 << 7):
                mapped |= XINPUT_START

            pov = int(info.dwPOV)
            if pov < 36000:
                if pov >= 31500 or pov <= 4500:
                    mapped |= XINPUT_DPAD_UP
                if 4500 <= pov <= 13500:
                    mapped |= XINPUT_DPAD_RIGHT
                if 13500 <= pov <= 22500:
                    mapped |= XINPUT_DPAD_DOWN
                if 22500 <= pov <= 31500:
                    mapped |= XINPUT_DPAD_LEFT

            lx = int(info.dwXpos) - 32768
            ly = -(int(info.dwYpos) - 32768)
            return mapped, lx, ly, name
        return None

    def _poll(self) -> None:
        now = time.monotonic()
        if now >= self._raw_check_at:
            self._raw_check_at = now + 0.9
            self._raw_name = _detect_rawinput_gamepad()

        reading = self._read_xinput()
        if reading is None:
            reading = self._read_winmm()

        now_connected = (reading is not None) or (self._raw_name is not None)
        det_name = (reading[3] if reading is not None else self._raw_name) or ""
        if now_connected != self._connected or (now_connected and det_name and det_name != self._device_name):
            was_connected = self._connected
            self._connected = now_connected
            self._device_name = det_name if now_connected else ""
            if now_connected != was_connected:
                self.connected_changed.emit(now_connected)
            self.device_changed.emit(now_connected, self._device_name)
            self._timer.setInterval(24 if now_connected else 250)

        parent = self.parent()
        if parent is not None and hasattr(parent, "isActiveWindow") and not parent.isActiveWindow():
            self._prev_buttons = 0
            self._repeat_dir = ""
            return

        if reading is None:
            self._prev_buttons = 0
            self._repeat_dir = ""
            return

        buttons, lx, ly, _name = reading
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
        if (buttons & XINPUT_DPAD_LEFT) or lx < -STICK_DEADZONE:
            direction = "left"
        elif (buttons & XINPUT_DPAD_RIGHT) or lx > STICK_DEADZONE:
            direction = "right"
        elif (buttons & XINPUT_DPAD_UP) or ly > STICK_DEADZONE:
            direction = "up"
        elif (buttons & XINPUT_DPAD_DOWN) or ly < -STICK_DEADZONE:
            direction = "down"

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
