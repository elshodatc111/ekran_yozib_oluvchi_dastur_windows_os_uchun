"""Dasturni ishga tushirish."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from . import APP_NAME, __version__, paths
from .core import winutil


def setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        paths.logs_dir() / "ekran_yozuvchi.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:
        root.addHandler(logging.StreamHandler())

    def hook(exc_type, exc, tb):  # noqa: ANN001
        logging.getLogger("uncaught").critical("Kutilmagan xato", exc_info=(exc_type, exc, tb))

    sys.excepthook = hook


def main() -> int:
    setup_logging()
    log = logging.getLogger("app")
    log.info("%s %s ishga tushdi", APP_NAME, __version__)

    if not winutil.acquire_single_instance():
        winutil.bring_existing_to_front(APP_NAME)
        return 0

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .config import Config
    from .core.audio_capture import AudioEngine
    from .core.recorder import Recorder
    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(True)
    font = QFont(theme.FONT_FAMILY)
    font.setPixelSize(13)
    app.setFont(font)
    app.setStyleSheet(theme.app_qss())
    from .ui.appicon import app_icon
    app.setWindowIcon(app_icon())

    try:
        config = Config()
        audio = AudioEngine()
        recorder = Recorder(config, audio)
        window = MainWindow(config, audio, recorder)
        window.place_initial()
        window.show()

        def late_init() -> None:
            audio.start(config["mic_device"], config["loopback_device"])
            window.audio.mic_muted = not config["mic_enabled"]
            window.audio.loop_muted = not config["loopback_enabled"]
            if recorder.ffmpeg:
                recorder.probe_async()
                QTimer.singleShot(2500, recorder.recover_orphans)
            else:
                window.show_notice("ffmpeg.exe topilmadi. «ffmpeg» papkasiga joylang "
                                   "(get_ffmpeg.ps1 ni ishga tushiring).", error=True)
            if audio.mic_error:
                window.show_notice("Mikrofon ochilmadi: " + audio.mic_error)
            window.settings.set_encoder_label(recorder.encoder_label())

        QTimer.singleShot(150, late_init)
    except Exception as e:  # noqa: BLE001
        log.exception("Ishga tushirishda xato")
        QMessageBox.critical(None, APP_NAME, f"Dastur ishga tushmadi:\n{e}")
        return 1

    code = app.exec()
    log.info("Dastur yopildi")
    return code
