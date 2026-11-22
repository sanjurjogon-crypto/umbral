from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import hashlib
import os
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QImage, QPixmap

from .paths import covers_dir

ICON_SIZE = 256


def _signature(path: str) -> str:
    try:
        stat = os.stat(path)
        stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        stamp = "0"
    return hashlib.sha1(f"{path.lower()}|{stamp}".encode("utf-8")).hexdigest()[:16]


def icons_dir() -> Path:
    path = covers_dir() / "icons"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extract(path: str, size: int = ICON_SIZE) -> Optional[QImage]:
    if os.name != "nt":
        return None
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
    except (AttributeError, OSError):
        return None

    user32.PrivateExtractIconsW.restype = ctypes.c_uint
    user32.PrivateExtractIconsW.argtypes = [
        wt.LPCWSTR,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(wt.HICON),
        ctypes.POINTER(ctypes.c_ushort),
        ctypes.c_uint,
        ctypes.c_uint,
    ]

    class BITMAP(ctypes.Structure):
        _fields_ = [
            ("bmType", wt.LONG),
            ("bmWidth", wt.LONG),
            ("bmHeight", wt.LONG),
            ("bmWidthBytes", wt.LONG),
            ("bmPlanes", wt.WORD),
            ("bmBitsPixel", wt.WORD),
            ("bmBits", ctypes.c_void_p),
        ]

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wt.BOOL),
            ("xHotspot", wt.DWORD),
            ("yHotspot", wt.DWORD),
            ("hbmMask", wt.HBITMAP),
            ("hbmColor", wt.HBITMAP),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wt.DWORD),
            ("biWidth", wt.LONG),
            ("biHeight", wt.LONG),
            ("biPlanes", wt.WORD),
            ("biBitCount", wt.WORD),
            ("biCompression", wt.DWORD),
            ("biSizeImage", wt.DWORD),
            ("biXPelsPerMeter", wt.LONG),
            ("biYPelsPerMeter", wt.LONG),
            ("biClrUsed", wt.DWORD),
            ("biClrImportant", wt.DWORD),
        ]

    handles = (wt.HICON * 1)()
    identifiers = (ctypes.c_ushort * 1)()
    try:
        count = user32.PrivateExtractIconsW(
            path, 0, size, size, handles, identifiers, 1, 0
        )
    except (OSError, ValueError):
        return None
    if not count or not handles[0]:
        return None

    hicon = handles[0]
    info = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(info)) or not info.hbmColor:
        user32.DestroyIcon(hicon)
        return None

    bitmaps = ctypes.c_void_p(int(info.hbmColor))

    bitmap = BITMAP()
    gdi32.GetObjectW.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p]
    gdi32.GetObjectW.restype = ctypes.c_int
    gdi32.GetObjectW(bitmaps, ctypes.sizeof(bitmap), ctypes.byref(bitmap))
    width = int(bitmap.bmWidth)
    height = int(bitmap.bmHeight)
    if width <= 0 or height <= 0:
        user32.DestroyIcon(hicon)
        return None

    hdc = user32.GetDC(0)
    memory = gdi32.CreateCompatibleDC(hdc)
    gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    gdi32.SelectObject.restype = wt.HGDIOBJ
    gdi32.GetDIBits.argtypes = [
        wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.SelectObject(memory, bitmaps)
    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(header)
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 32
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory, bitmaps, 0, height, buffer, ctypes.byref(header), 0)
    image = QImage(buffer, width, height, QImage.Format_RGBA8888).copy()

    gdi32.DeleteDC(memory)
    user32.ReleaseDC(0, hdc)
    user32.DestroyIcon(hicon)
    return image if not image.isNull() else None


def exe_icon(executable: str) -> Optional[Path]:
    if not executable:
        return None
    exe = Path(executable)
    if not exe.is_file():
        return None
    target = icons_dir() / f"exe-{_signature(str(exe))}.png"
    if target.is_file():
        return target
    image = _extract(str(exe))
    if image is None:
        return None
    try:
        if image.save(str(target), "PNG") and target.is_file():
            return target
    except (OSError, ValueError):
        return None
    return None


def exe_pixmap(executable: str) -> Optional[QPixmap]:
    path = exe_icon(executable)
    if path is None:
        return None
    pixmap = QPixmap(str(path))
    return None if pixmap.isNull() else pixmap
