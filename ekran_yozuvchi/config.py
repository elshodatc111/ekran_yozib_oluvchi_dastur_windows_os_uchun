"""Sozlamalar (JSON fayl, %APPDATA%\\EkranYozuvchi\\config.json)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .paths import appdata_dir

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "output_dir": "",            # bo'sh bo'lsa, standart papka tanlanadi
    "lesson_name": "",           # ixtiyoriy dars nomi (fayl nomiga qo'shiladi)
    "monitor_index": 0,          # 0 = birinchi monitor (asosiy)
    "profile": "auto",           # auto | yengil | standart | yuqori
    "encoder_mode": "auto",      # auto | cpu
    "mic_enabled": True,
    "loopback_enabled": True,
    "mic_device": "",            # bo'sh = standart qurilma
    "loopback_device": "",       # bo'sh = standart dinamik
    "show_cursor": True,
    "countdown": False,          # 3-2-1 sanash
    "exclude_from_capture": True,
    "window_x": None,
    "window_y": None,
}


class Config:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (appdata_dir() / "config.json")
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            if self.path.is_file():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for key in DEFAULTS:
                        if key in raw:
                            self.data[key] = raw[key]
        except Exception:
            log.exception("Sozlamalarni o'qib bo'lmadi, standart qiymatlar ishlatiladi")

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception:
            log.exception("Sozlamalarni saqlab bo'lmadi")

    def get(self, key: str) -> Any:
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self.data[key] = value
        if save:
            self.save()

    def __getitem__(self, key: str) -> Any:
        return self.get(key)
