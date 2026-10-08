"""Sozlamalar oynasi (har bir o'zgarish darhol saqlanadi)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from ..config import Config
from ..core import disk, winutil
from ..core.audio_capture import list_input_devices, list_loopback_devices
from ..core.profiles import PROFILE_CHOICES
from ..core.video_capture import list_monitors


def _section(text: str) -> QLabel:
    lb = QLabel(text.upper())
    lb.setProperty("section", True)
    return lb


class SettingsDialog(QDialog):
    changed = Signal(str)        # o'zgargan sozlama kaliti

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = config
        self.setWindowTitle("Sozlamalar")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint
                            | Qt.WindowTitleHint | Qt.CustomizeWindowHint)
        self.setMinimumWidth(430)
        self._loading = True

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)

        # --- saqlash
        root.addWidget(_section("Saqlash"))
        row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_btn = QPushButton("Tanlash...")
        self.folder_btn.clicked.connect(self._choose_folder)
        row.addWidget(self.folder_edit, 1)
        row.addWidget(self.folder_btn)
        root.addLayout(row)
        self.stats_label = QLabel("")
        self.stats_label.setProperty("muted", True)
        open_btn = QPushButton("Papkani ochish")
        open_btn.clicked.connect(lambda: winutil.open_path(str(self._folder())))
        srow = QHBoxLayout()
        srow.addWidget(self.stats_label, 1)
        srow.addWidget(open_btn)
        root.addLayout(srow)

        root.addSpacing(4)
        root.addWidget(QLabel("Dars nomi (ixtiyoriy, fayl nomiga qo'shiladi)"))
        self.lesson_edit = QLineEdit()
        self.lesson_edit.setPlaceholderText("Masalan: Ingliz_tili_guruh_3")
        self.lesson_edit.setMaxLength(60)
        self.lesson_edit.editingFinished.connect(
            lambda: self._set("lesson_name", self.lesson_edit.text().strip()))
        root.addWidget(self.lesson_edit)

        # --- video
        root.addSpacing(6)
        root.addWidget(_section("Video"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.monitor_combo = QComboBox()
        self.profile_combo = QComboBox()
        grid.addWidget(QLabel("Monitor"), 0, 0)
        grid.addWidget(self.monitor_combo, 0, 1)
        grid.addWidget(QLabel("Sifat"), 1, 0)
        grid.addWidget(self.profile_combo, 1, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid)
        self.encoder_label = QLabel("Kodlovchi: aniqlanmoqda...")
        self.encoder_label.setProperty("muted", True)
        root.addWidget(self.encoder_label)
        self.cpu_check = QCheckBox("Faqat protsessor bilan kodlash (video karta ishlatilmasin)")
        root.addWidget(self.cpu_check)
        self.cursor_check = QCheckBox("Sichqoncha kursorini yozuvga qo'shish")
        root.addWidget(self.cursor_check)

        # --- ovoz
        root.addSpacing(6)
        root.addWidget(_section("Ovoz"))
        agrid = QGridLayout()
        agrid.setHorizontalSpacing(10)
        agrid.setVerticalSpacing(8)
        self.mic_combo = QComboBox()
        self.loop_combo = QComboBox()
        agrid.addWidget(QLabel("Mikrofon"), 0, 0)
        agrid.addWidget(self.mic_combo, 0, 1)
        agrid.addWidget(QLabel("Dinamik"), 1, 0)
        agrid.addWidget(self.loop_combo, 1, 1)
        agrid.setColumnStretch(1, 1)
        root.addLayout(agrid)

        # --- boshqa
        root.addSpacing(6)
        root.addWidget(_section("Boshqa"))
        self.countdown_check = QCheckBox("Yozishdan oldin 3-2-1 sanash")
        self.exclude_check = QCheckBox("Dastur oynasi yozuvda ko'rinmasin (Windows 10 2004+)")
        root.addWidget(self.countdown_check)
        root.addWidget(self.exclude_check)

        self.lock_label = QLabel("Yozuv paytida sozlamalarni o'zgartirib bo'lmaydi.")
        self.lock_label.setStyleSheet("color:#FFB84D;")
        self.lock_label.hide()
        root.addWidget(self.lock_label)

        self._locked_widgets = [self.folder_btn, self.lesson_edit, self.monitor_combo, self.profile_combo,
                                self.cpu_check, self.cursor_check, self.mic_combo, self.loop_combo]

        self._populate()
        self._connect()
        self._loading = False

    # ------------------------------------------------------------------ to'ldirish
    def _folder(self) -> Path:
        d = (self.cfg["output_dir"] or "").strip()
        return Path(d) if d else disk.default_output_dir()

    def _populate(self) -> None:
        self.folder_edit.setText(str(self._folder()))
        self.lesson_edit.setText(self.cfg["lesson_name"] or "")

        self.monitor_combo.clear()
        mons = list_monitors()
        if not mons:
            self.monitor_combo.addItem("Asosiy monitor", 0)
        for m in mons:
            self.monitor_combo.addItem(m.label, m.index)
        self._select(self.monitor_combo, self.cfg["monitor_index"])

        self.profile_combo.clear()
        for key, title in PROFILE_CHOICES:
            self.profile_combo.addItem(title, key)
        self._select(self.profile_combo, self.cfg["profile"])

        self.mic_combo.clear()
        self.mic_combo.addItem("Standart mikrofon", "")
        for n in list_input_devices():
            self.mic_combo.addItem(n, n)
        self._select(self.mic_combo, self.cfg["mic_device"])

        self.loop_combo.clear()
        self.loop_combo.addItem("Standart dinamik / quloqchin", "")
        for n in list_loopback_devices():
            self.loop_combo.addItem(n.replace(" [Loopback]", ""), n)
        self._select(self.loop_combo, self.cfg["loopback_device"])

        self.cpu_check.setChecked(self.cfg["encoder_mode"] == "cpu")
        self.cursor_check.setChecked(bool(self.cfg["show_cursor"]))
        self.countdown_check.setChecked(bool(self.cfg["countdown"]))
        self.exclude_check.setChecked(bool(self.cfg["exclude_from_capture"]))
        self.refresh_stats()

    @staticmethod
    def _select(combo: QComboBox, value) -> None:
        i = combo.findData(value)
        combo.setCurrentIndex(i if i >= 0 else 0)

    def _connect(self) -> None:
        self.monitor_combo.currentIndexChanged.connect(
            lambda: self._set("monitor_index", self.monitor_combo.currentData()))
        self.profile_combo.currentIndexChanged.connect(
            lambda: self._set("profile", self.profile_combo.currentData()))
        self.mic_combo.currentIndexChanged.connect(
            lambda: self._set("mic_device", self.mic_combo.currentData()))
        self.loop_combo.currentIndexChanged.connect(
            lambda: self._set("loopback_device", self.loop_combo.currentData()))
        self.cpu_check.toggled.connect(lambda v: self._set("encoder_mode", "cpu" if v else "auto"))
        self.cursor_check.toggled.connect(lambda v: self._set("show_cursor", bool(v)))
        self.countdown_check.toggled.connect(lambda v: self._set("countdown", bool(v)))
        self.exclude_check.toggled.connect(lambda v: self._set("exclude_from_capture", bool(v)))

    def _set(self, key: str, value) -> None:
        if self._loading:
            return
        self.cfg.set(key, value)
        self.changed.emit(key)

    # ------------------------------------------------------------------ amallar
    def _choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Videolar saqlanadigan papkani tanlang", str(self._folder()))
        if d:
            d = str(Path(d))
            self.folder_edit.setText(d)
            self._set("output_dir", d)
            self.refresh_stats()

    def refresh_stats(self) -> None:
        folder = self._folder()
        count, total = disk.folder_stats(folder)
        free = disk.free_bytes(folder)
        self.stats_label.setText(f"Papkada: {count} ta video, {disk.format_size(total)} · "
                                 f"bo'sh joy: {disk.format_size(free)}")

    def set_encoder_label(self, text: str) -> None:
        self.encoder_label.setText(f"Kodlovchi: {text}")

    def set_locked(self, locked: bool) -> None:
        for w in self._locked_widgets:
            w.setEnabled(not locked)
        self.lock_label.setVisible(locked)

    def showEvent(self, e) -> None:  # noqa: N802
        self.refresh_stats()
        super().showEvent(e)
