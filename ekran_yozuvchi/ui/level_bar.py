"""Ovoz darajasi chizig'i va "MIK / DIN" qatori."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from . import theme
from .widgets import IconButton


class LevelBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(11)
        self.setMinimumWidth(60)
        self._level = 0.0
        self._peak = 0.0
        self._muted = False
        self._hint = ""
        self._font = QFont(theme.FONT_FAMILY)
        self._font.setPixelSize(9)

    def set_state(self, level: float, peak: float, muted: bool, hint: str) -> None:
        if (abs(level - self._level) < 0.004 and abs(peak - self._peak) < 0.004
                and muted == self._muted and hint == self._hint):
            return
        self._level, self._peak, self._muted, self._hint = level, peak, muted, hint
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.PANEL))
        p.drawRoundedRect(r, 5, 5)
        if self._muted:
            return
        if self._level > 0.005:
            g = QLinearGradient(0, 0, r.width(), 0)
            g.setColorAt(0.0, QColor(theme.GREEN))
            g.setColorAt(0.7, QColor(theme.GREEN))
            g.setColorAt(0.88, QColor(theme.AMBER))
            g.setColorAt(1.0, QColor(theme.RED))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 0, max(8.0, r.width() * self._level), r.height()), 5, 5)
        if self._peak > 0.03:
            x = min(r.width() - 2, r.width() * self._peak)
            p.setBrush(QColor(theme.TEXT))
            p.drawRoundedRect(QRectF(x - 1, 1, 2, r.height() - 2), 1, 1)
        if self._hint:
            p.setFont(self._font)
            p.setPen(QColor(theme.MUTED))
            p.drawText(r, Qt.AlignCenter, self._hint)


class LevelRow(QWidget):
    """[MIK] [██████░░░░] [ikonka-tugma]. Tugma ovozni o'chiradi/yoqadi."""

    toggled = Signal(bool)     # True = yoqilgan (eshitiladi/yoziladi)

    def __init__(self, label: str, icon_on: str, icon_off: str, tooltip: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon_on, self._icon_off = icon_on, icon_off
        self._enabled = True
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        self.label = QLabel(label)
        self.label.setFixedWidth(26)
        self.label.setStyleSheet(f"color:{theme.MUTED}; font-size:10px; font-weight:600;")
        self.bar = LevelBar()
        self.button = IconButton(icon_on, 22, tooltip)
        self.button.clicked.connect(self._clicked)
        lay.addWidget(self.label)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.button)

    def set_enabled_audio(self, on: bool) -> None:
        self._enabled = on
        self.button.set_kind(self._icon_on if on else self._icon_off)

    def is_audio_enabled(self) -> bool:
        return self._enabled

    def _clicked(self) -> None:
        self.set_enabled_audio(not self._enabled)
        self.toggled.emit(self._enabled)

    def update_level(self, level: float, peak: float, hint: str) -> None:
        self.bar.set_state(level, peak, not self._enabled, hint)
