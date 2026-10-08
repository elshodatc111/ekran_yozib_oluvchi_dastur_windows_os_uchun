"""Dastur papkalari va FFmpeg joylashuvi."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_DIR_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Dastur joylashgan papka (PyInstaller bilan yig'ilgan bo'lsa, .exe papkasi)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    p = Path(base) / APP_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = appdata_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def find_ffmpeg() -> str | None:
    """ffmpeg.exe faqat dastur papkasidan qidiriladi (xavfsizlik talabi).

    Ishlab chiqish rejimida (PyInstaller'siz) sinov uchun EKRAN_FFMPEG
    muhit o'zgaruvchisi ham qabul qilinadi.
    """
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates = [app_dir() / "ffmpeg" / exe, app_dir() / exe]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "ffmpeg" / exe)
    for c in candidates:
        if c.is_file():
            return str(c)
    if not is_frozen():
        override = os.environ.get("EKRAN_FFMPEG")
        if override and Path(override).is_file():
            return override
    return None
