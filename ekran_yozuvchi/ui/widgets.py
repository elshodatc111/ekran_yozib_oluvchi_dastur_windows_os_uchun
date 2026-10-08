"""O'zimiz chizadigan oddiy vidjetlar: holat nuqtasi, taymer, tugmalar, progress."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from . import theme
from .icons import draw_icon


class StatusDot(QWidget):
    """Holat nuqtasi: kutish (kulrang), yozish (qizil, miltillaydi), pauza (sariq), saqlash (ko'k)."""

    COLORS = {"idle": theme.MUTED, "recording": theme.RED, "paused": theme.AMBER, "saving": theme.BLUE}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._mode = "idle"
        self._on = True
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._blink)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._on = True
        if mode == "recording":
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _blink(self) -> None:
        self._on = not self._on
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self.COLORS.get(self._mode, theme.MUTED))
        if self._mode == "recording" and not self._on:
            c.setAlpha(60)
        p.setPen(Qt.NoPen)
        halo = QColor(c)
        halo.setAlpha(min(c.alpha(), 55))
        p.setBrush(halo)
        p.drawEllipse(self.rect().center(), 6, 6)
        p.setBrush(c)
        p.drawEllipse(self.rect().center(), 4, 4)


class TimerLabel(QWidget):
    """HH:MM:SS — raqamlar kengligi qat'iy, shuning uchun matn "sakramaydi"."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = "00:00:00"
        self._mode = "idle"
        self._font = QFont(theme.FONT_FAMILY)
        self._font.setPixelSize(28)
        self._font.setWeight(QFont.DemiBold)
        fm = QFontMetrics(self._font)
        self._digit_w = max(fm.horizontalAdvance(str(d)) for d in range(10))
        self._colon_w = int(fm.horizontalAdvance(":") * 0.9)
        self.setFixedHeight(fm.height() + 4)
        self.setMinimumWidth(self._digit_w * 6 + self._colon_w * 2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_text(self, text: str) -> None:
        if text != self._text:
            self._text = text
            self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self._font)
        color = {"recording": theme.TEXT, "paused": theme.AMBER, "saving": theme.BLUE}.get(self._mode, theme.MUTED)
        p.setPen(QColor(color))
        total = sum(self._colon_w if ch == ":" else self._digit_w for ch in self._text)
        x = (self.width() - total) / 2
        h = self.height()
        for ch in self._text:
            w = self._colon_w if ch == ":" else self._digit_w
            p.drawText(QRectF(x, 0, w, h), Qt.AlignCenter, ch)
            x += w


class IconButton(QAbstractButton):
    def __init__(self, kind: str, size: int = 30, tooltip: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self._size = size
        self.hover_color = QColor(theme.PANEL_HOVER)
        self.icon_color = QColor(theme.MUTED)
        self.icon_hover_color = QColor(theme.TEXT)
        self._hover = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._size, self._size)

    def enterEvent(self, e) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._hover and self.isEnabled():
            p.setPen(Qt.NoPen)
            p.setBrush(self.hover_color)
            p.drawRoundedRect(self.rect(), 8, 8)
        color = self.icon_hover_color if (self._hover and self.isEnabled()) else self.icon_color
        if not self.isEnabled():
            color = QColor(theme.BORDER)
        pad = self._size * 0.18
        draw_icon(p, self.kind, QRectF(self.rect()).adjusted(pad, pad, -pad, -pad), color)


class PillButton(QAbstractButton):
    """Katta yumaloq tugma: ikonka + matn. variant: primary (qizil), neutral, danger."""

    def __init__(self, text: str, icon: str = "", variant: str = "neutral",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.icon_kind = icon
        self.variant = variant
        self._hover = False
        self._font = QFont(theme.FONT_FAMILY)
        self._font.setPixelSize(12)
        self._font.setWeight(QFont.DemiBold)
        self.setFixedHeight(34)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_content(self, text: str, icon: str, variant: str | None = None) -> None:
        self.setText(text)
        self.icon_kind = icon
        if variant:
            self.variant = variant
        self.update()

    def enterEvent(self, e) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        enabled = self.isEnabled()
        if self.variant == "primary":
            bg = QColor(theme.RED_HOVER if self._hover else theme.RED)
            fg = QColor("#FFFFFF")
        else:
            bg = QColor(theme.PANEL_HOVER if self._hover else theme.PANEL)
            fg = QColor(theme.TEXT)
        if not enabled:
            bg = QColor(theme.PANEL)
            fg = QColor(theme.MUTED)
        p.setPen(Qt.NoPen if self.variant == "primary" and enabled else QColor(theme.BORDER))
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        p.setFont(self._font)
        fm = QFontMetrics(self._font)
        tw = fm.horizontalAdvance(self.text())
        icon_w = 16 if self.icon_kind else 0
        gap = 6 if self.icon_kind else 0
        total = icon_w + gap + tw
        x = (self.width() - total) / 2
        if self.icon_kind:
            draw_icon(p, self.icon_kind, QRectF(x, (self.height() - icon_w) / 2, icon_w, icon_w), fg)
        p.setPen(fg)
        p.drawText(QRectF(x + icon_w + gap, 0, tw + 4, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())


class ProgressStrip(QWidget):
    """Ingichka progress chizig'i (saqlash jarayoni uchun)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self.setFixedHeight(6)

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(self.rect())
        p.setBrush(QColor(theme.PANEL))
        p.drawRoundedRect(r, 3, 3)
        if self._value > 0:
            p.setBrush(QColor(theme.BLUE))
            p.drawRoundedRect(QRectF(0, 0, max(6.0, r.width() * self._value), r.height()), 3, 3)
