"""Windows API yordamchilari (ctypes). Windows bo'lmagan tizimda xavfsiz "bo'sh" ishlaydi."""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys

log = logging.getLogger(__name__)

IS_WIN = sys.platform == "win32"

if IS_WIN:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    _user32.GetCursorPos.restype = wintypes.BOOL
    _user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    _user32.FindWindowW.restype = wintypes.HWND
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _kernel32.SetThreadExecutionState.argtypes = [wintypes.DWORD]
    _kernel32.SetThreadExecutionState.restype = wintypes.DWORD
    _kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
    ]
    _kernel32.GetVolumeInformationW.restype = wintypes.BOOL
    _kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetDriveTypeW.restype = wintypes.UINT

_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_HWND_TOPMOST = -1
_WDA_NONE = 0x00
_WDA_EXCLUDEFROMCAPTURE = 0x11
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002
_SW_RESTORE = 9

CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0

_mutex_handle = None


def windows_build() -> int:
    if not IS_WIN:
        return 0
    try:
        return int(sys.getwindowsversion().build)  # type: ignore[attr-defined]
    except Exception:
        return 0


def subprocess_kwargs() -> dict:
    """Konsol oynasi chiqmasligi uchun subprocess parametrlari."""
    if not IS_WIN:
        return {}
    si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
    si.wShowWindow = 0
    return {"creationflags": CREATE_NO_WINDOW, "startupinfo": si}


def set_topmost(hwnd: int) -> bool:
    """Oynani barcha oynalar ustida ushlab turadi (fokus olmasdan)."""
    if not IS_WIN or not hwnd:
        return False
    try:
        return bool(_user32.SetWindowPos(
            wintypes.HWND(int(hwnd)), wintypes.HWND(_HWND_TOPMOST), 0, 0, 0, 0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE))
    except Exception:
        log.exception("SetWindowPos xatosi")
        return False


def set_exclude_from_capture(hwnd: int, enable: bool) -> bool:
    """Dastur oynasi yozuvga (va Zoom ekran ulashishiga) tushmasligi uchun.

    Faqat Windows 10 (2004, build 19041) va undan yangi tizimda ishlaydi.
    """
    if not IS_WIN or not hwnd or windows_build() < 19041:
        return False
    try:
        return bool(_user32.SetWindowDisplayAffinity(
            wintypes.HWND(int(hwnd)), _WDA_EXCLUDEFROMCAPTURE if enable else _WDA_NONE))
    except Exception:
        log.exception("SetWindowDisplayAffinity xatosi")
        return False


def prevent_sleep(enable: bool) -> None:
    """Yozish paytida kompyuter uxlab qolmasligi uchun (shu oqimdan chaqirilishi kerak)."""
    if not IS_WIN:
        return
    try:
        flags = _ES_CONTINUOUS
        if enable:
            flags |= _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
        _kernel32.SetThreadExecutionState(flags)
    except Exception:
        log.exception("SetThreadExecutionState xatosi")


def get_cursor_pos() -> tuple[int, int] | None:
    if not IS_WIN:
        return None
    try:
        pt = wintypes.POINT()
        if _user32.GetCursorPos(ctypes.byref(pt)):
            return int(pt.x), int(pt.y)
    except Exception:
        pass
    return None


def is_fat32(path: str) -> bool:
    """Berilgan yo'l joylashgan disk FAT32 bo'lsa True (4 GB dan katta fayl yozib bo'lmaydi)."""
    if not IS_WIN:
        return False
    try:
        drive = os.path.splitdrive(os.path.abspath(path))[0]
        if not drive:
            return False
        root = drive + "\\"
        fs_name = ctypes.create_unicode_buffer(32)
        ok = _kernel32.GetVolumeInformationW(root, None, 0, None, None, None, fs_name, 32)
        return bool(ok) and fs_name.value.upper() == "FAT32"
    except Exception:
        return False


def fixed_drives() -> list[str]:
    """Ichki (qattiq) disklar ro'yxati, masalan ['C:\\\\', 'D:\\\\']."""
    if not IS_WIN:
        return []
    out: list[str] = []
    try:
        mask = _kernel32.GetLogicalDrives()
        for i in range(26):
            if mask & (1 << i):
                root = f"{chr(65 + i)}:\\"
                if _kernel32.GetDriveTypeW(root) == 3:  # DRIVE_FIXED
                    out.append(root)
    except Exception:
        log.exception("Disklarni aniqlab bo'lmadi")
    return out


def acquire_single_instance(name: str = "EkranYozuvchi_SingleInstance") -> bool:
    """Dastur ikkinchi marta ishga tushmasligi uchun. True = bu birinchi nusxa."""
    global _mutex_handle
    if not IS_WIN:
        return True
    try:
        _mutex_handle = _kernel32.CreateMutexW(None, False, "Local\\" + name)
        return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def bring_existing_to_front(title: str) -> None:
    if not IS_WIN:
        return
    try:
        hwnd = _user32.FindWindowW(None, title)
        if hwnd:
            _user32.ShowWindow(hwnd, _SW_RESTORE)
            _user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def open_path(path: str) -> None:
    """Papka yoki faylni standart dastur bilan ochadi."""
    try:
        if IS_WIN:
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        log.exception("Ochib bo'lmadi: %s", path)


def reveal_file(path: str) -> None:
    """Explorer'da faylni belgilab ko'rsatadi."""
    try:
        if IS_WIN:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            open_path(os.path.dirname(path))
    except Exception:
        log.exception("Explorer ochilmadi")
