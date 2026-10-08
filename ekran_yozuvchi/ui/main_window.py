"""Asosiy kichik oyna: doim eng ustida, holat, taymer, ovoz darajasi, boshqaruv."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
                               QWidget)

from .. import APP_NAME
from ..config import Config
from ..core import disk, winutil
from ..core.audio_capture import AudioEngine
from ..core.recorder import Recorder, State
from . import theme
from .level_bar import LevelRow
from .settings_panel import SettingsDialog
from .widgets import IconButton, PillButton, ProgressStrip, StatusDot, TimerLabel

log = logging.getLogger(__name__)

STATUS_TEXT = {
    State.IDLE: "Tayyor",
    State.RECORDING: "Yozilmoqda",
    State.PAUSED: "Pauza",
    State.SAVING: "Saqlanmoqda...",
}
SILENCE_HINT_AFTER = 10.0


class MainWindow(QWidget):
    def __init__(self, config: Config, audio: AudioEngine, recorder: Recorder) -> None:
        super().__init__()
        self.cfg = config
        self.audio = audio
        self.rec = recorder
        self._last_file: str = ""
        self._quit_after_save = False
        self._countdown_left = 0
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(lambda: self.notice_label.hide())
        self._drag_ok = False

        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(264)

        self.settings = SettingsDialog(config, self)
        self.settings.changed.connect(self._on_setting_changed)

        self._build_ui()
        self._wire()
        self._apply_state(State.IDLE.value)
        self.audio.mic_muted = not self.cfg["mic_enabled"]
        self.audio.loop_muted = not self.cfg["loopback_enabled"]
        self.mic_row.set_enabled_audio(bool(self.cfg["mic_enabled"]))
        self.loop_row.set_enabled_audio(bool(self.cfg["loopback_enabled"]))

        self._fast = QTimer(self)
        self._fast.setInterval(50)
        self._fast.timeout.connect(self._tick_fast)
        self._fast.start()
        self._slow = QTimer(self)
        self._slow.setInterval(1000)
        self._slow.timeout.connect(self._tick_slow)
        self._slow.start()
        self._pos_timer = QTimer(self)
        self._pos_timer.setSingleShot(True)
        self._pos_timer.setInterval(600)
        self._pos_timer.timeout.connect(self._save_pos)

    # ------------------------------------------------------------------ qurish
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.body = QWidget()
        self.body.setObjectName("body")
        outer.addWidget(self.body)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(12, 8, 10, 12)
        lay.setSpacing(6)

        # sarlavha
        head = QHBoxLayout()
        head.setSpacing(5)
        self.dot = StatusDot()
        self.status_label = QLabel("Tayyor")
        self.status_label.setStyleSheet("font-weight:600; font-size:12px;")
        head.addWidget(self.dot)
        head.addWidget(self.status_label)
        head.addStretch(1)
        self.settings_btn = IconButton("gear", 24, "Sozlamalar")
        self.min_btn = IconButton("minimize", 24, "Kichraytirish")
        self.close_btn = IconButton("close", 24, "Yopish")
        for b in (self.settings_btn, self.min_btn, self.close_btn):
            head.addWidget(b)
        lay.addLayout(head)

        # taymer
        self.timer = TimerLabel()
        lay.addWidget(self.timer)

        # ovoz
        self.mic_row = LevelRow("MIK", "mic", "mic_off", "Mikrofonni yoqish/o'chirish")
        self.loop_row = LevelRow("DIN", "speaker", "speaker_off", "Kompyuter ovozini yoqish/o'chirish")
        lay.addWidget(self.mic_row)
        lay.addWidget(self.loop_row)

        # ma'lumot qatori
        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")
        lay.addWidget(self.info_label)

        # tugmalar
        btns = QHBoxLayout()
        btns.setSpacing(6)
        self.main_btn = PillButton("Yozishni boshlash", "rec", "primary")
        self.stop_btn = PillButton("To'xtatish", "stop", "neutral")
        btns.addWidget(self.main_btn, 1)
        btns.addWidget(self.stop_btn, 1)
        lay.addLayout(btns)

        # saqlash progressi
        self.progress = ProgressStrip()
        lay.addWidget(self.progress)

        # saqlangandan keyingi qator
        self.after_box = QWidget()
        al = QVBoxLayout(self.after_box)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(6)
        self.after_label = QLabel("")
        self.after_label.setWordWrap(True)
        self.after_label.setStyleSheet(f"color:{theme.GREEN}; font-size:11px; font-weight:600;")
        arow = QHBoxLayout()
        arow.setSpacing(6)
        self.open_folder_btn = QPushButton("Papkani ochish")
        self.open_video_btn = QPushButton("Videoni ochish")
        small = "padding:3px 6px; min-height:18px; font-size:11px; border-radius:7px;"
        self.open_folder_btn.setStyleSheet(small)
        self.open_video_btn.setStyleSheet(small)
        arow.addWidget(self.open_folder_btn)
        arow.addWidget(self.open_video_btn)
        al.addWidget(self.after_label)
        al.addLayout(arow)
        lay.addWidget(self.after_box)

        # ogohlantirish
        self.notice_label = QLabel("")
        self.notice_label.setWordWrap(True)
        self.notice_label.setMaximumWidth(240)
        lay.addWidget(self.notice_label)

        self.progress.hide()
        self.after_box.hide()
        self.notice_label.hide()

    def _wire(self) -> None:
        self.close_btn.clicked.connect(self.close)
        self.min_btn.clicked.connect(self.showMinimized)
        self.settings_btn.clicked.connect(self._open_settings)
        self.main_btn.clicked.connect(self._on_main_clicked)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.mic_row.toggled.connect(self._on_mic_toggled)
        self.loop_row.toggled.connect(self._on_loop_toggled)
        self.open_folder_btn.clicked.connect(self._open_folder)
        self.open_video_btn.clicked.connect(self._open_video)
        r = self.rec
        r.state_changed.connect(self._apply_state)
        r.saved.connect(self._on_saved)
        r.error.connect(lambda m: self.show_notice(m, error=True))
        r.notice.connect(lambda m: self.show_notice(m))
        r.progress.connect(self._on_progress)
        r.encoder_ready.connect(lambda _n: self.settings.set_encoder_label(self.rec.encoder_label()))

    def _fit(self) -> None:
        """Kenglik qat'iy, balandlik tarkibga qarab o'zgaradi."""
        lay = self.layout()
        lay.activate()
        h = lay.totalHeightForWidth(self.width()) if lay.hasHeightForWidth() else -1
        if h <= 0:
            h = lay.sizeHint().height()
        self.setFixedHeight(h)

    # ------------------------------------------------------------------ chizish
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(theme.BG))
        p.setPen(QColor(theme.BORDER))
        p.drawRoundedRect(r, 14, 14)

    # ------------------------------------------------------------------ sichqoncha (oynani surish)
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            wh = self.windowHandle()
            if wh is not None:
                wh.startSystemMove()
        super().mousePressEvent(e)

    def moveEvent(self, e) -> None:  # noqa: N802
        self._pos_timer.start()
        super().moveEvent(e)

    def _save_pos(self) -> None:
        p = self.pos()
        self.cfg.set("window_x", p.x(), save=False)
        self.cfg.set("window_y", p.y())

    # ------------------------------------------------------------------ ko'rsatish
    def place_initial(self) -> None:
        x, y = self.cfg["window_x"], self.cfg["window_y"]
        screens = QGuiApplication.screens()
        if x is not None and y is not None:
            from PySide6.QtCore import QPoint
            pt = QPoint(int(x), int(y))
            if any(s.availableGeometry().contains(pt) for s in screens):
                self.move(pt)
                return
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self._fit()
        self.move(geo.right() - self.width() - 24, geo.top() + 24)

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        QTimer.singleShot(0, self._apply_window_flags)

    def _hwnds(self) -> list[int]:
        out = [int(self.winId())]
        if self.settings.isVisible():
            out.append(int(self.settings.winId()))
        return out

    def _apply_window_flags(self) -> None:
        for h in self._hwnds():
            winutil.set_topmost(h)
            winutil.set_exclude_from_capture(h, bool(self.cfg["exclude_from_capture"]))

    # ------------------------------------------------------------------ davriy yangilash
    def _tick_fast(self) -> None:
        mic, loop = self.audio.levels()
        mic_hint = self._hint(self.audio.mic_meter.silence_seconds(), self.audio.mic_available(),
                              self.audio.mic_error, self.mic_row.is_audio_enabled())
        loop_hint = self._hint(self.audio.loop_meter.silence_seconds(), self.audio.loop_available(),
                               self.audio.loop_error, self.loop_row.is_audio_enabled())
        self.mic_row.update_level(mic, self.audio.mic_meter.peak(), mic_hint)
        self.loop_row.update_level(loop, self.audio.loop_meter.peak(), loop_hint)
        if self._countdown_left <= 0:
            self.timer.set_text(disk.format_duration(self.rec.elapsed()))

    @staticmethod
    def _hint(silence: float, available: bool, error: str, enabled: bool) -> str:
        if not enabled:
            return ""
        if not available:
            return "Qurilma topilmadi"
        return "Ovoz yo'q" if silence > SILENCE_HINT_AFTER else ""

    def _tick_slow(self) -> None:
        for h in self._hwnds():
            winutil.set_topmost(h)
        self.rec.tick()
        st = self.rec.status()
        if self.rec.state in (State.RECORDING, State.PAUSED):
            self.info_label.setText(f"{disk.format_size(st['size'])} · bo'sh joy {disk.format_size(st['free'])}")
        elif self.rec.state == State.IDLE:
            self.info_label.setText(f"Bo'sh joy: {disk.format_size(st['free'])}")

    # ------------------------------------------------------------------ holat
    def _apply_state(self, state: str) -> None:
        st = State(state)
        self.status_label.setText(STATUS_TEXT[st])
        self.dot.set_mode(st.value)
        self.timer.set_mode(st.value)
        self.settings.set_locked(st != State.IDLE)
        recording = st in (State.RECORDING, State.PAUSED)

        if st == State.IDLE:
            self.main_btn.set_content("Yozishni boshlash", "rec", "primary")
        elif st == State.RECORDING:
            self.main_btn.set_content("Pauza", "pause", "neutral")
        elif st == State.PAUSED:
            self.main_btn.set_content("Davom etish", "play", "primary")
        self.main_btn.setEnabled(st != State.SAVING)
        self.stop_btn.setVisible(recording or st == State.SAVING)
        self.stop_btn.setEnabled(recording)
        self.progress.setVisible(st == State.SAVING)
        if st == State.SAVING:
            self.progress.set_value(0.0)
        if st in (State.RECORDING,) and self.after_box.isVisible():
            self.after_box.hide()
        if st == State.IDLE:
            self.timer.set_text("00:00:00") if not self._last_file else None
            if self._quit_after_save:
                QTimer.singleShot(300, self.close)
        self._fit()

    def _on_progress(self, p: float) -> None:
        self.progress.set_value(p)
        self.status_label.setText(f"Saqlanmoqda... {int(p * 100)}%")

    def _on_saved(self, path: str) -> None:
        self._last_file = path
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = 0
        self.after_label.setText(f"Saqlandi: {Path(path).name}  ({disk.format_size(size)})")
        self.after_box.show()
        self.timer.set_text(disk.format_duration(self.rec.elapsed()))
        self.settings.refresh_stats()
        self._fit()

    # ------------------------------------------------------------------ ogohlantirishlar
    def show_notice(self, text: str, error: bool = False) -> None:
        color = theme.RED if error else theme.AMBER
        self.notice_label.setStyleSheet(
            f"color:{color}; font-size:11px; background:{theme.PANEL}; border-radius:8px; padding:5px 8px;")
        self.notice_label.setText(text)
        self.notice_label.show()
        self._notice_timer.start(20000 if error else 12000)
        self._fit()

    # ------------------------------------------------------------------ tugmalar
    def _on_main_clicked(self) -> None:
        st = self.rec.state
        if st == State.IDLE:
            self.notice_label.hide()
            if self._countdown_left > 0:
                return
            if self.cfg["countdown"]:
                self._start_countdown()
            else:
                self._begin()
        elif st in (State.RECORDING, State.PAUSED):
            self.rec.toggle_pause()

    def _begin(self) -> None:
        self.after_box.hide()
        self._last_file = ""
        self.audio.mic_meter.reset_silence()
        self.audio.loop_meter.reset_silence()
        self.rec.start()
        self._fit()

    def _start_countdown(self) -> None:
        self._countdown_left = 3
        self.main_btn.setEnabled(False)
        self.settings.set_locked(True)
        self._countdown_step()

    def _countdown_step(self) -> None:
        if self._countdown_left > 0:
            self.timer.set_text(f"{self._countdown_left}")
            self._countdown_left -= 1
            QTimer.singleShot(1000, self._countdown_step)
        else:
            self.main_btn.setEnabled(True)
            self.settings.set_locked(False)
            self.timer.set_text("00:00:00")
            self._begin()

    def _confirm(self, title: str, text: str, yes: str, no: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Question)
        box.setText(text)
        yb = box.addButton(yes, QMessageBox.AcceptRole)
        box.addButton(no, QMessageBox.RejectRole)
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        box.exec()
        return box.clickedButton() is yb

    def _on_stop_clicked(self) -> None:
        if self.rec.state not in (State.RECORDING, State.PAUSED):
            return
        if self.rec.elapsed() > 30:
            if not self._confirm("Yozuvni to'xtatish", "Yozuv to'xtatilib, video saqlansinmi?",
                                 "Ha, saqlash", "Yo'q, davom etish"):
                return
        self.rec.stop()

    def _on_mic_toggled(self, on: bool) -> None:
        self.audio.mic_muted = not on
        self.cfg.set("mic_enabled", on)

    def _on_loop_toggled(self, on: bool) -> None:
        self.audio.loop_muted = not on
        self.cfg.set("loopback_enabled", on)

    def _open_folder(self) -> None:
        if self._last_file:
            winutil.reveal_file(self._last_file)
        else:
            winutil.open_path(str(self.rec.output_dir()))

    def _open_video(self) -> None:
        if self._last_file:
            winutil.open_path(self._last_file)

    # ------------------------------------------------------------------ sozlamalar
    def _open_settings(self) -> None:
        if self.settings.isVisible():
            self.settings.raise_()
            return
        self.settings.show()
        geo = self.frameGeometry()
        screen = QGuiApplication.screenAt(geo.center()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        w = self.settings.sizeHint().width()
        x = geo.left() - w - 12
        if x < avail.left():
            x = geo.right() + 12
        self.settings.move(max(avail.left(), min(x, avail.right() - w)), geo.top())
        QTimer.singleShot(0, self._apply_window_flags)

    def _on_setting_changed(self, key: str) -> None:
        if key in ("mic_device", "loopback_device"):
            self.audio.restart_sources(self.cfg["mic_device"], self.cfg["loopback_device"])
        elif key == "exclude_from_capture":
            self._apply_window_flags()
        elif key == "encoder_mode":
            self.settings.set_encoder_label(self.rec.encoder_label())
        elif key == "output_dir":
            self.rec.recover_orphans()

    # ------------------------------------------------------------------ yopish
    def closeEvent(self, e) -> None:  # noqa: N802
        st = self.rec.state
        if st in (State.RECORDING, State.PAUSED):
            if self._confirm("Dasturni yopish", "Yozuv davom etmoqda. Yozuvni to'xtatib, saqlab, "
                             "so'ng dasturni yopamizmi?", "Ha, saqlab yopish", "Yo'q, davom etish"):
                self._quit_after_save = True
                self.rec.stop()
            e.ignore()
            return
        if st == State.SAVING:
            self._quit_after_save = True
            self.show_notice("Video saqlanmoqda. Tugagach dastur o'zi yopiladi.")
            e.ignore()
            return
        self._save_pos()
        self.settings.close()
        self.audio.stop()
        e.accept()
