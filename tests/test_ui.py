"""Interfeys tutun testi (oynasiz, offscreen). Skrinshotni TEST_SHOT_DIR ga saqlaydi."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ekran_yozuvchi.config import Config
from ekran_yozuvchi.core.recorder import Recorder, State
from ekran_yozuvchi.ui import theme
from ekran_yozuvchi.ui.main_window import MainWindow
from tests.test_integration import FakeAudio, FakeGrabber, pump


class UiSmoke(unittest.TestCase):
    def test_flow(self):
        app = QApplication.instance() or QApplication([])
        app.setStyleSheet(theme.app_qss())
        tmp = tempfile.mkdtemp()
        cfg = Config(Path(tmp) / "c.json")
        cfg.set("output_dir", tmp + "/out")
        cfg.set("profile", "yengil")
        audio = FakeAudio()
        audio.start()
        rec = Recorder(cfg, audio, ffmpeg=os.environ.get("EKRAN_FFMPEG"), grabber_factory=lambda i: FakeGrabber(i))
        win = MainWindow(cfg, audio, rec)
        win.place_initial()
        win.show()
        shots = os.environ.get("TEST_SHOT_DIR")

        def shot(name):
            pump(app, 0.3)
            if shots:
                win.grab().save(str(Path(shots) / f"{name}.png"))

        shot("1_idle")
        win.main_btn.click()
        pump(app, 2.5)
        self.assertEqual(rec.state, State.RECORDING)
        shot("2_recording")
        win.main_btn.click()
        self.assertEqual(rec.state, State.PAUSED)
        shot("3_paused")
        win.main_btn.click()
        win.mic_row.button.click()
        self.assertTrue(audio.mic_muted)
        win.show_notice("Diskda bo'sh joy kam: 3.2 GB.")
        shot("4_notice")
        rec.stop()
        pump(app, 0.3)
        self.assertIn(rec.state, (State.SAVING, State.IDLE))
        end = time.monotonic() + 60
        while rec.state != State.IDLE and time.monotonic() < end:
            pump(app, 0.1)
        pump(app, 0.5)
        shot("5_saved")
        self.assertTrue(win.after_box.isVisible())
        win.settings.show()
        pump(app, 0.3)
        if shots:
            win.settings.grab().save(str(Path(shots) / "6_settings.png"))
        win.settings.close()
        win._quit_after_save = False
        win.close()


if __name__ == "__main__":
    unittest.main()
