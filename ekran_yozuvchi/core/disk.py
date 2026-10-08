"""Disk, fayl nomi va vaqt/hajm formatlash yordamchilari."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from . import winutil

TEMP_DIR_NAME = "_vaqtinchalik"
GB = 1024 ** 3
MB = 1024 ** 2

MIN_FREE_TO_START = 1 * GB       # shundan kam bo'lsa yozishni boshlamaymiz
WARN_FREE = 5 * GB               # shundan kam bo'lsa ogohlantiramiz
CRITICAL_FREE = 300 * MB         # yozish paytida shundan kam qolsa to'xtatamiz


def free_bytes(path: str | Path) -> int:
    """Berilgan yo'l joylashgan diskdagi bo'sh joy (mavjud bo'lmasa, eng yaqin ota-papka)."""
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except Exception:
        return 0


def format_size(n: float) -> str:
    if n >= GB:
        return f"{n / GB:.1f} GB"
    if n >= MB:
        return f"{n / MB:.0f} MB"
    return f"{n / 1024:.0f} KB"


def format_duration(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def default_output_dir() -> Path:
    """Standart papka: tizim diskidan boshqa eng bo'sh joyi ko'p ichki disk, bo'lmasa ~/Videos."""
    import os

    system_drive = (os.environ.get("SystemDrive") or "C:").upper() + "\\"
    drives = winutil.fixed_drives()
    others = [d for d in drives if d.upper() != system_drive]
    pool = others or drives
    if pool:
        best = max(pool, key=free_bytes)
        return Path(best) / "Yozuvlar"
    return Path.home() / "Videos" / "Yozuvlar"


_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_name(text: str, limit: int = 60) -> str:
    text = _BAD_CHARS.sub("", text or "").strip().strip(".")
    text = re.sub(r"\s+", "_", text)
    return text[:limit]


def make_recording_name(lesson: str = "", now: datetime | None = None) -> str:
    now = now or datetime.now()
    stem = now.strftime("%Y-%m-%d_%H-%M-%S")
    lesson = sanitize_name(lesson)
    return f"{stem}_{lesson}" if lesson else stem


def unique_path(folder: Path, stem: str, ext: str = ".mp4") -> Path:
    p = folder / f"{stem}{ext}"
    i = 2
    while p.exists():
        p = folder / f"{stem}_{i}{ext}"
        i += 1
    return p


def folder_stats(folder: str | Path) -> tuple[int, int]:
    """(videolar soni, jami hajm) - faqat papkaning o'zidagi .mp4 fayllar."""
    count = 0
    total = 0
    try:
        for f in Path(folder).iterdir():
            if f.is_file() and f.suffix.lower() == ".mp4":
                count += 1
                total += f.stat().st_size
    except Exception:
        pass
    return count, total


def cleanup_temp_root(out_dir: Path) -> None:
    """_vaqtinchalik papkasi bo'sh bo'lsa, o'chirib tashlaydi."""
    root = out_dir / TEMP_DIR_NAME
    try:
        if root.is_dir() and not any(root.iterdir()):
            root.rmdir()
    except Exception:
        pass
