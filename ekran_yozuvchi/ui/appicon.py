"""Dastur ikonkasi (kod bilan chiziladi) va .ico fayl yaratish."""

from __future__ import annotations

import struct

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap

from . import theme


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.BG))
    p.drawRoundedRect(QRectF(s * 0.04, s * 0.04, s * 0.92, s * 0.92), s * 0.22, s * 0.22)
    pen = QPen(QColor(theme.RED), s * 0.07)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(s * 0.2, s * 0.2, s * 0.6, s * 0.6))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.RED))
    p.drawEllipse(QRectF(s * 0.36, s * 0.36, s * 0.28, s * 0.28))
    p.end()
    return img


def app_icon() -> QIcon:
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(render(sz)))
    return icon


def write_ico(path: str) -> None:
    """Bir nechta o'lchamli (PNG ichida) .ico fayl yozadi."""
    sizes = (16, 24, 32, 48, 64, 128, 256)
    blobs = []
    for sz in sizes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        render(sz).save(buf, "PNG")
        blobs.append(bytes(ba))
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for sz, data in zip(sizes, blobs):
        w = 0 if sz >= 256 else sz
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(head + entries + b"".join(blobs))
