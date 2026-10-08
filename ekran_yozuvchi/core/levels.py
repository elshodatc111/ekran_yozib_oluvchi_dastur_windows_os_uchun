"""Ovoz darajasi (indikator) hisoblari."""

from __future__ import annotations

import math
import time

import numpy as np

FLOOR_DB = -60.0
LOUD_THRESHOLD = 0.12          # shundan yuqori daraja "ovoz bor" hisoblanadi
STALE_AFTER = 0.25             # shu vaqt yangilanish bo'lmasa, daraja 0 ga tushadi


def level_from_amplitude(amp: float) -> float:
    """Amplituda (0..1) ni -60..0 dB shkalasi bo'yicha 0..1 darajaga o'tkazadi."""
    if amp <= 1e-5:
        return 0.0
    db = 20.0 * math.log10(min(amp, 1.0))
    return max(0.0, min(1.0, (db - FLOOR_DB) / -FLOOR_DB))


def block_level(samples: np.ndarray) -> float:
    """Blok uchun daraja (RMS va pik aralashmasi)."""
    if samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float32))))
    peak = float(np.max(np.abs(samples)))
    return level_from_amplitude(max(rms * 1.8, peak * 0.6))


class LevelMeter:
    """Silliqlangan daraja: tez ko'tariladi, sekin tushadi."""

    def __init__(self) -> None:
        self._value = 0.0
        self._peak = 0.0
        self._peak_time = 0.0
        self._updated = 0.0
        self.last_loud = time.monotonic()

    def update(self, samples: np.ndarray) -> None:
        self.update_level(block_level(samples))

    def update_level(self, lv: float) -> None:
        now = time.monotonic()
        if lv >= self._value:
            self._value = lv
        else:
            self._value = max(lv, self._value - 0.06)
        if lv >= self._peak:
            self._peak = lv
            self._peak_time = now
        self._updated = now
        if lv > LOUD_THRESHOLD:
            self.last_loud = now

    def reset_silence(self) -> None:
        self.last_loud = time.monotonic()

    def value(self) -> float:
        if time.monotonic() - self._updated > STALE_AFTER:
            return 0.0
        return self._value

    def peak(self) -> float:
        now = time.monotonic()
        if now - self._updated > STALE_AFTER:
            return 0.0
        if now - self._peak_time > 1.0:
            self._peak = max(self._value, self._peak - 0.02)
        return self._peak

    def silence_seconds(self) -> float:
        return time.monotonic() - self.last_loud
