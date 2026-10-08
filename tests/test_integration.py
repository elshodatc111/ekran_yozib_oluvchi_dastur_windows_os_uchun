"""Integratsiya testi: soxta ekran + soxta ovoz + haqiqiy ffmpeg.
Ishga tushirish:  EKRAN_FFMPEG=/yo'l/ffmpeg python -m unittest tests.test_integration
(Windows'da ffmpeg\\ffmpeg.exe avtomatik topiladi.)"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication as QCoreApplication

from ekran_yozuvchi import paths
from ekran_yozuvchi.config import Config
from ekran_yozuvchi.core import winutil
from ekran_yozuvchi.core.audio_capture import AudioEngine
from ekran_yozuvchi.core.recorder import Recorder, State
from ekran_yozuvchi.core.video_capture import ScreenGrabber


class FakeGrabber(ScreenGrabber):
    def open(self):
        self.backend = "fake"
        self.width, self.height = 640, 360
        self.n = 0

    def first_frame(self, timeout=4.0):
        return self._frame()

    def _frame(self):
        f = np.zeros((360, 640, 4), dtype=np.uint8)
        f[:, :, 0] = (self.n * 5) % 256
        f[:, :, 1] = 80
        f[:, :, 3] = 255
        return f

    def grab(self):
        self.n += 1
        time.sleep(0.004)
        return self._frame() if self.n % 3 else None   # ba'zan "yangi kadr yo'q"

    def close(self):
        pass


class FakeSource:
    def __init__(self, buf, freq):
        self.buf, self.freq = buf, freq
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        t = 0
        while not self._stop.is_set():
            x = (0.3 * np.sin(2 * np.pi * self.freq * (t + np.arange(480)) / 48000)).astype(np.float32)
            self.buf.write(x)
            t += 480
            time.sleep(0.01)

    def stop(self):
        self._stop.set()


class FakeAudio(AudioEngine):
    def _make_mic(self, name):
        return FakeSource(self.mic_buf, 440)

    def _make_loop(self, name):
        return FakeSource(self.loop_buf, 880)


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                         capture_output=True, text=True).stdout
    return json.loads(out)


class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])
        cls.ffmpeg = paths.find_ffmpeg()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = Config(Path(self.tmp) / "cfg.json")
        self.cfg.set("output_dir", str(Path(self.tmp) / "out"))
        self.cfg.set("profile", "yengil")
        self.audio = FakeAudio()
        self.audio.start()
        self.rec = Recorder(self.cfg, self.audio, ffmpeg=self.ffmpeg, grabber_factory=lambda i: FakeGrabber(i))
        self.saved, self.errors = [], []
        self.rec.saved.connect(self.saved.append)
        self.rec.error.connect(self.errors.append)

    def tearDown(self):
        self.audio.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wait_saved(self, timeout=60):
        end = time.monotonic() + timeout
        while time.monotonic() < end and not self.saved and not self.errors:
            pump(self.app, 0.1)

    def test_record_pause_stop(self):
        self.assertIsNotNone(self.ffmpeg, "ffmpeg topilmadi (EKRAN_FFMPEG ni bering)")
        self.assertTrue(self.rec.start(), self.errors)
        self.assertEqual(self.rec.state, State.RECORDING)
        pump(self.app, 2.0)
        self.rec.toggle_pause()
        self.assertEqual(self.rec.state, State.PAUSED)
        pump(self.app, 1.5)              # pauza: yozuvga kirmasligi kerak
        self.rec.toggle_pause()
        pump(self.app, 2.0)
        el = self.rec.elapsed()
        self.assertAlmostEqual(el, 4.0, delta=0.3)
        self.rec.stop()
        self.assertEqual(self.rec.state, State.SAVING)
        self._wait_saved()
        self.assertFalse(self.errors, self.errors)
        self.assertEqual(len(self.saved), 1)
        path = self.saved[0]
        info = probe(path)
        kinds = {s["codec_type"]: s for s in info["streams"]}
        self.assertEqual(kinds["video"]["codec_name"], "h264")
        self.assertEqual(kinds["audio"]["codec_name"], "aac")
        dur = float(info["format"]["duration"])
        self.assertAlmostEqual(dur, 4.0, delta=0.6)
        self.assertEqual(int(kinds["video"]["width"]) % 2, 0)
        # vaqtinchalik fayllar tozalangan
        self.assertFalse((Path(self.tmp) / "out" / "_vaqtinchalik").exists())
        # ovoz bor (jim emas)
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-af", "volumedetect", "-vn", "-f", "null", "-"],
                           capture_output=True, text=True)
        self.assertNotIn("mean_volume: -91", r.stderr)

    def test_cursor_drawn(self):
        winutil_orig = winutil.get_cursor_pos
        try:
            from ekran_yozuvchi.core import recorder as rmod
            rmod.winutil.get_cursor_pos = lambda: (100, 100)
            self.assertTrue(self.rec.start())
            pump(self.app, 1.0)
            self.rec.stop()
            self._wait_saved()
            self.assertFalse(self.errors, self.errors)
        finally:
            winutil.get_cursor_pos = winutil_orig

    def test_crash_recovery(self):
        self.assertTrue(self.rec.start())
        pump(self.app, 4.0)
        # jarayon "o'ldi"ni taqlid qilish: ish oqimlarini to'xtatmasdan fayllarni nusxalaymiz
        tmp_root = Path(self.tmp) / "out" / "_vaqtinchalik"
        d = next(tmp_root.iterdir())
        crash = Path(self.tmp) / "crash"
        shutil.copytree(d, crash)
        self.rec.stop()
        self._wait_saved()
        pump(self.app, 0.5)
        self.assertEqual(self.rec.state, State.IDLE)
        # nusxani yangi "_vaqtinchalik" ga qo'yib, tiklashni sinaymiz
        root2 = Path(self.tmp) / "out" / "_vaqtinchalik"
        root2.mkdir(parents=True, exist_ok=True)
        shutil.copytree(crash, root2 / "2020-01-01_00-00-00")
        notes = []
        self.rec.notice.connect(notes.append)
        self.rec.recover_orphans()
        end = time.monotonic() + 30
        while time.monotonic() < end and not notes:
            pump(self.app, 0.1)
        self.assertTrue(notes, "tiklash xabari yo'q")
        recovered = list((Path(self.tmp) / "out").glob("tiklangan_*.mp4"))
        self.assertEqual(len(recovered), 1)
        self.assertGreater(float(probe(str(recovered[0]))["format"]["duration"]), 0.5)

    def test_no_ffmpeg_error(self):
        rec = Recorder(self.cfg, self.audio, ffmpeg="")
        rec._ffmpeg = ""
        errs = []
        rec.error.connect(errs.append)
        rec._ffmpeg = None
        old = paths.find_ffmpeg
        paths.find_ffmpeg = lambda: None
        try:
            self.assertFalse(rec.start())
        finally:
            paths.find_ffmpeg = old
        self.assertTrue(errs)


if __name__ == "__main__":
    unittest.main()
