"""Sifat profillari."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    key: str
    title: str
    fps: int
    max_height: int
    x264_preset: str
    crf: int          # libx264 sifati (kichik = yaxshi)
    cq: int           # NVENC / AMF / QSV sifati
    maxrate: str
    bufsize: str


PROFILES: dict[str, Profile] = {
    "yengil": Profile("yengil", "Yengil (720p, 15 kadr/s)", 15, 720, "ultrafast", 26, 28, "2500k", "5000k"),
    "standart": Profile("standart", "Standart (1080p, 24 kadr/s)", 24, 1080, "veryfast", 24, 26, "5M", "10M"),
    "yuqori": Profile("yuqori", "Yuqori (1080p, 30 kadr/s)", 30, 1080, "faster", 21, 23, "8M", "16M"),
}

PROFILE_CHOICES = [("auto", "Avto (tavsiya etiladi)")] + [(k, p.title) for k, p in PROFILES.items()]


def resolve_profile(key: str, encoder: str) -> Profile:
    """'auto' bo'lsa: video karta bilan kodlashda Standart, protsessor bilan Yengil."""
    if key in PROFILES:
        return PROFILES[key]
    return PROFILES["yengil"] if encoder == "libx264" else PROFILES["standart"]


def compute_output_size(width: int, height: int, max_height: int) -> tuple[int, int]:
    """Chiqish o'lchami: balandlik max_height dan oshmaydi, ikkala son juft bo'ladi."""
    if height > max_height:
        out_h = max_height
        out_w = round(width * max_height / height)
    else:
        out_w, out_h = width, height
    out_w -= out_w % 2
    out_h -= out_h % 2
    return max(out_w, 2), max(out_h, 2)
