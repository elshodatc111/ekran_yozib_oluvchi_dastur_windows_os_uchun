"""Birlik testlari (Windows kerak emas):  python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ekran_yozuvchi.core import disk
from ekran_yozuvchi.core.audio_capture import AudioBuffer, LinearResampler, WavWriter, repair_wav
from ekran_yozuvchi.core.levels import LevelMeter, level_from_amplitude
from ekran_yozuvchi.core.profiles import compute_output_size, resolve_profile
from ekran_yozuvchi.core.video_capture import CursorPainter


class Units(unittest.TestCase):
    def test_buffer_zero_fill_and_order(self):
        b = AudioBuffer()
        b.write(np.arange(1, 6, dtype=np.float32))
        out = b.read(5)
        self.assertEqual(list(out), [1, 2, 3, 4, 5])
        b.write(np.arange(1, 4, dtype=np.float32))
        out = b.read(5)                 # 3 ta bor, 5 ta so'raladi -> oxiri nol
        self.assertEqual(list(out), [1, 2, 3, 0, 0])

    def test_buffer_priming(self):
        b = AudioBuffer()
        b.write(np.ones(10, dtype=np.float32))
        self.assertEqual(float(b.read(10, latency=5).sum()), 0.0)   # hali tayyor emas
        b.write(np.ones(10, dtype=np.float32))
        self.assertEqual(float(b.read(10, latency=5).sum()), 10.0)

    def test_buffer_trim(self):
        b = AudioBuffer()
        b.write(np.ones(1000, dtype=np.float32))
        b.trim(100)
        self.assertEqual(b.available, 100)

    def test_resampler_length_and_continuity(self):
        r = LinearResampler(44100, 48000)
        t = np.arange(44100, dtype=np.float32)
        x = np.sin(2 * np.pi * 440 * t / 44100).astype(np.float32)
        out = np.concatenate([r.process(x[i:i + 441]) for i in range(0, 44100, 441)])
        self.assertAlmostEqual(len(out), 48000, delta=3)
        ref = np.sin(2 * np.pi * 440 * np.arange(len(out)) / 48000)
        self.assertLess(float(np.max(np.abs(out[10:] - ref[10:]))), 0.02)

    def test_resampler_passthrough(self):
        r = LinearResampler(48000, 48000)
        x = np.ones(10, dtype=np.float32)
        self.assertIs(r.process(x), x)

    def test_profiles(self):
        self.assertEqual(compute_output_size(1920, 1080, 1080), (1920, 1080))
        self.assertEqual(compute_output_size(2560, 1440, 1080), (1920, 1080))
        self.assertEqual(compute_output_size(1366, 768, 720), (1280, 720))
        self.assertEqual(compute_output_size(1921, 1081, 2000), (1920, 1080))
        self.assertEqual(resolve_profile("auto", "libx264").key, "yengil")
        self.assertEqual(resolve_profile("auto", "h264_nvenc").key, "standart")
        self.assertEqual(resolve_profile("yuqori", "libx264").key, "yuqori")

    def test_disk_helpers(self):
        self.assertEqual(disk.format_duration(3725), "01:02:05")
        self.assertEqual(disk.sanitize_name('A/B:C*? d'), "ABC_d")
        self.assertTrue(disk.make_recording_name("Dars 1").endswith("_Dars_1"))
        with tempfile.TemporaryDirectory() as d:
            p = disk.unique_path(Path(d), "x")
            p.write_bytes(b"1")
            self.assertEqual(disk.unique_path(Path(d), "x").name, "x_2.mp4")
            self.assertEqual(disk.folder_stats(d)[0], 1)
            self.assertGreater(disk.free_bytes(Path(d) / "nonexistent" / "deep"), 0)

    def test_levels(self):
        self.assertEqual(level_from_amplitude(0), 0.0)
        self.assertAlmostEqual(level_from_amplitude(1.0), 1.0)
        self.assertGreater(level_from_amplitude(0.1), level_from_amplitude(0.01))
        m = LevelMeter()
        m.update(np.full(480, 0.5, dtype=np.float32))
        self.assertGreater(m.value(), 0.5)

    def test_wav_repair(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.wav")
            w = WavWriter(p)
            w.write(b"\x00\x01" * 4800)
            w._f.flush()
            w._f.close()          # sarlavhani yangilamasdan (uzilishni taqlid)
            self.assertTrue(repair_wav(p))
            import wave
            with wave.open(p) as wf:
                self.assertEqual(wf.getnframes(), 2400)
                self.assertEqual(wf.getframerate(), 48000)

    def test_cursor_painter_roundtrip(self):
        frame = np.full((100, 120, 4), 77, dtype=np.uint8)
        orig = frame.copy()
        cp = CursorPainter()
        saved = cp.draw(frame, 10, 10)
        self.assertFalse(np.array_equal(frame, orig))
        cp.restore(frame, saved)
        self.assertTrue(np.array_equal(frame, orig))
        # chetga chiqib ketgan holat
        saved = cp.draw(frame, 118, 98)
        cp.restore(frame, saved)
        self.assertTrue(np.array_equal(frame, orig))
        self.assertIsNone(cp.draw(frame, 500, 500))


if __name__ == "__main__":
    unittest.main()
