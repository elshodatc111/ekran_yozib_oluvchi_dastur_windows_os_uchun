"""Ekranni olish: dxcam (Desktop Duplication, GPU) — zaxira: mss. Kursor qo'lda chiziladi.

Barcha kadrlar BGRA (4 kanal, uint8) ko'rinishida qaytariladi — FFmpeg `-pix_fmt bgra`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class MonitorInfo:
    index: int
    left: int
    top: int
    width: int
    height: int

    @property
    def label(self) -> str:
        return f"Monitor {self.index + 1} ({self.width}x{self.height})"


def list_monitors() -> list[MonitorInfo]:
    """Monitorlar ro'yxati (mss orqali)."""
    try:
        import mss
        with mss.mss() as sct:
            mons = sct.monitors[1:]
            return [MonitorInfo(i, m["left"], m["top"], m["width"], m["height"])
                    for i, m in enumerate(mons)]
    except Exception:
        log.exception("Monitorlar ro'yxatini olib bo'lmadi")
        return []


# --------------------------------------------------------------------------- kursor

def _polygon_mask(points: list[tuple[float, float]], w: int, h: int) -> np.ndarray:
    ys, xs = np.mgrid[0:h, 0:w]
    xs = xs + 0.5
    ys = ys + 0.5
    inside = np.zeros((h, w), dtype=bool)
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        if y1 == y2:
            continue
        cond = ((y1 > ys) != (y2 > ys)) & (xs < (x2 - x1) * (ys - y1) / (y2 - y1) + x1)
        inside ^= cond
    return inside


class CursorPainter:
    """Standart o'q-kursor (oq, qora chegarali). Kadrga chizadi va keyin tiklaydi."""

    ARROW = [(0, 0), (0, 17), (4.2, 13.2), (7.2, 20), (9.8, 18.9), (6.9, 12.4), (12.2, 12.4)]

    def __init__(self, scale: float = 1.0) -> None:
        pad = 2
        pts = [(x * scale + pad, y * scale + pad) for x, y in self.ARROW]
        w = int(13 * scale) + pad * 2 + 1
        h = int(21 * scale) + pad * 2 + 1
        fill = _polygon_mask(pts, w, h)
        dil = fill.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                dil |= np.roll(np.roll(fill, dy, axis=0), dx, axis=1)
        self.pad = pad
        self.mask = dil
        self.sprite = np.zeros((h, w, 4), dtype=np.uint8)
        self.sprite[dil] = (0, 0, 0, 255)
        self.sprite[fill] = (255, 255, 255, 255)

    def draw(self, frame: np.ndarray, x: int, y: int):
        """x, y — kursor nuqtasi kadr koordinatalarida. Tiklash uchun ma'lumot qaytaradi."""
        fh, fw = frame.shape[:2]
        sh, sw = self.sprite.shape[:2]
        x -= self.pad
        y -= self.pad
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + sw, fw), min(y + sh, fh)
        if x1 <= x0 or y1 <= y0:
            return None
        region = frame[y0:y1, x0:x1]
        saved = region.copy()
        m = self.mask[y0 - y:y1 - y, x0 - x:x1 - x]
        sp = self.sprite[y0 - y:y1 - y, x0 - x:x1 - x]
        channels = frame.shape[2] if frame.ndim == 3 else 1
        region[m] = sp[m][:, :channels]
        return (y0, y1, x0, x1, saved)

    @staticmethod
    def restore(frame: np.ndarray, saved) -> None:
        if saved is None:
            return
        y0, y1, x0, x1, data = saved
        frame[y0:y1, x0:x1] = data


# --------------------------------------------------------------------------- ekran olish

class ScreenGrabber:
    """Bitta monitordan kadr oladi. Yangi kadr bo'lmasa, grab() None qaytaradi."""

    def __init__(self, monitor_index: int = 0) -> None:
        self.monitor_index = monitor_index
        self.backend = ""
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0
        self._cam = None
        self._sct = None
        self._errors = 0

    # -- ochish
    def open(self) -> None:
        mons = list_monitors()
        if mons:
            idx = self.monitor_index if 0 <= self.monitor_index < len(mons) else 0
            m = mons[idx]
            self.monitor_index = idx
            self.left, self.top, self.width, self.height = m.left, m.top, m.width, m.height
        try:
            self._open_dxcam()
            return
        except Exception as e:  # noqa: BLE001
            log.warning("dxcam ochilmadi (%s), mss ishlatiladi", e)
            self._close_dxcam()
        self._open_mss()

    def _open_dxcam(self) -> None:
        import dxcam
        cam = dxcam.create(device_idx=0, output_idx=self.monitor_index, output_color="BGRA")
        if cam is None:
            raise RuntimeError("dxcam.create None qaytardi")
        self._cam = cam
        self.backend = "dxcam"

    def _close_dxcam(self) -> None:
        cam, self._cam = self._cam, None
        if cam is not None:
            try:
                cam.release()
            except Exception:
                pass

    def _open_mss(self) -> None:
        import mss
        self._sct = mss.mss()
        self.backend = "mss"

    # -- kadr olish
    def grab(self) -> np.ndarray | None:
        try:
            frame = self._grab_once()
            self._errors = 0
            return frame
        except Exception as e:  # noqa: BLE001
            self._errors += 1
            log.warning("Kadr olishda xato (%d): %s", self._errors, e)
            if self._errors > 8:
                raise
            time.sleep(0.2)
            try:
                self.close()
                self.open()
            except Exception:
                log.exception("Qayta ochib bo'lmadi")
            return None

    def _grab_once(self) -> np.ndarray | None:
        if self.backend == "dxcam":
            return self._cam.grab()
        mon = {"left": self.left, "top": self.top, "width": self.width, "height": self.height}
        shot = self._sct.grab(mon)
        arr = np.frombuffer(bytearray(shot.bgra), dtype=np.uint8).reshape(shot.height, shot.width, 4)
        return arr

    def first_frame(self, timeout: float = 4.0) -> np.ndarray:
        """Birinchi kadrni kutadi va o'lchamni aniqlaydi."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            f = self.grab()
            if f is not None:
                self.height, self.width = f.shape[:2]
                return f
            time.sleep(0.03)
        raise RuntimeError("Ekrandan kadr olib bo'lmadi")

    def close(self) -> None:
        self._close_dxcam()
        s, self._sct = self._sct, None
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
