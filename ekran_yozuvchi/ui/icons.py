"""QPainter bilan chiziladigan ikonkalar (tashqi fayllar kerak emas)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen


def _pen(color: QColor, w: float) -> QPen:
    pen = QPen(color, w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def draw_icon(p: QPainter, kind: str, r: QRectF, color: QColor) -> None:
    """r — ikonka kvadrati. kind: gear, close, minimize, pause, play, stop, rec, folder,
    video, mic, mic_off, speaker, speaker_off, check."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    s = min(r.width(), r.height())
    cx, cy = r.center().x(), r.center().y()
    u = s / 24.0                       # 24x24 birlik tarmog'i
    ox, oy = cx - 12 * u, cy - 12 * u

    def pt(x: float, y: float) -> QPointF:
        return QPointF(ox + x * u, oy + y * u)

    stroke = _pen(color, 1.9 * u)
    p.setPen(stroke)
    p.setBrush(Qt.NoBrush)

    if kind == "close":
        p.drawLine(pt(6, 6), pt(18, 18))
        p.drawLine(pt(18, 6), pt(6, 18))
    elif kind == "minimize":
        p.drawLine(pt(6, 12), pt(18, 12))
    elif kind == "gear":
        p.drawEllipse(pt(12, 12), 4.2 * u, 4.2 * u)
        p.drawEllipse(pt(12, 12), 7.2 * u, 7.2 * u)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(pt(12 + 7.2 * math.cos(a), 12 + 7.2 * math.sin(a)),
                       pt(12 + 9.6 * math.cos(a), 12 + 9.6 * math.sin(a)))
    elif kind == "pause":
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(ox + 6 * u, oy + 5 * u, 4 * u, 14 * u), 1.2 * u, 1.2 * u)
        p.drawRoundedRect(QRectF(ox + 14 * u, oy + 5 * u, 4 * u, 14 * u), 1.2 * u, 1.2 * u)
    elif kind == "play":
        path = QPainterPath()
        path.moveTo(pt(8, 5))
        path.lineTo(pt(19, 12))
        path.lineTo(pt(8, 19))
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path)
    elif kind == "stop":
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(ox + 6 * u, oy + 6 * u, 12 * u, 12 * u), 2.2 * u, 2.2 * u)
    elif kind == "rec":
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(pt(12, 12), 6.5 * u, 6.5 * u)
    elif kind == "check":
        p.drawPolyline([pt(5.5, 12.5), pt(10, 17), pt(18.5, 7.5)])
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(pt(3.5, 7))
        path.lineTo(pt(9.5, 7))
        path.lineTo(pt(11.5, 9.2))
        path.lineTo(pt(20.5, 9.2))
        path.lineTo(pt(20.5, 18.5))
        path.lineTo(pt(3.5, 18.5))
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "video":
        p.drawRoundedRect(QRectF(ox + 3.5 * u, oy + 6 * u, 17 * u, 12 * u), 2.5 * u, 2.5 * u)
        path = QPainterPath()
        path.moveTo(pt(10.5, 9.5))
        path.lineTo(pt(14.5, 12))
        path.lineTo(pt(10.5, 14.5))
        path.closeSubpath()
        p.setBrush(color)
        p.drawPath(path)
    elif kind in ("mic", "mic_off"):
        p.drawRoundedRect(QRectF(ox + 9 * u, oy + 3.5 * u, 6 * u, 11 * u), 3 * u, 3 * u)
        p.drawArc(QRectF(ox + 5.5 * u, oy + 7.5 * u, 13 * u, 11 * u), 180 * 16, 180 * 16)
        p.drawLine(pt(12, 18.5), pt(12, 21))
        p.drawLine(pt(9, 21), pt(15, 21))
        if kind == "mic_off":
            p.setPen(_pen(QColor("#FF4D5E"), 2.1 * u))
            p.drawLine(pt(4.5, 4.5), pt(19.5, 19.5))
    elif kind in ("speaker", "speaker_off"):
        path = QPainterPath()
        path.moveTo(pt(4, 9.5))
        path.lineTo(pt(8, 9.5))
        path.lineTo(pt(13, 5))
        path.lineTo(pt(13, 19))
        path.lineTo(pt(8, 14.5))
        path.lineTo(pt(4, 14.5))
        path.closeSubpath()
        p.drawPath(path)
        if kind == "speaker":
            p.drawArc(QRectF(ox + 10 * u, oy + 8 * u, 8 * u, 8 * u), -60 * 16, 120 * 16)
            p.drawArc(QRectF(ox + 8 * u, oy + 5 * u, 14 * u, 14 * u), -60 * 16, 120 * 16)
        else:
            p.setPen(_pen(QColor("#FF4D5E"), 2.1 * u))
            p.drawLine(pt(4.5, 4.5), pt(19.5, 19.5))
    p.restore()
