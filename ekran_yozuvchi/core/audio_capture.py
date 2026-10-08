"""Ovoz yozish: mikrofon (sounddevice/WASAPI) + kompyuter ovozi (PyAudioWPatch loopback).

Ikkala manba 48 kHz mono float32 ga keltiriladi, har 20 ms da soat bo'yicha aralashtiriladi
va audio.wav (16-bit, stereo, 48 kHz) fayliga yoziladi. Manba ovoz bermasa (masalan,
kompyuterda hech narsa chalinmayotgan bo'lsa), o'rniga sukunat yoziladi — shuning uchun
ovoz va video hech qachon sinxronligini yo'qotmaydi.
"""

from __future__ import annotations

import logging
import struct
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

from .levels import LevelMeter, block_level

log = logging.getLogger(__name__)

RATE = 48000
TICK = 0.02
PRIME_LATENCY = 0.04            # manba bufer to'lgunicha shuncha kutiladi (uzilishlarni kamaytiradi)
MAX_BACKLOG = 0.30              # bufer shundan oshsa, ortiqchasi tashlanadi (soat siljishi)


# --------------------------------------------------------------------------- bufer / resampler

class AudioBuffer:
    """Oqimlararo xavfsiz mono float32 bufer."""

    def __init__(self, max_seconds: float = 3.0, rate: int = RATE) -> None:
        self._chunks: deque[np.ndarray] = deque()
        self._n = 0
        self._lock = threading.Lock()
        self._max = int(max_seconds * rate)
        self._primed = False

    @property
    def available(self) -> int:
        return self._n

    def write(self, a: np.ndarray) -> None:
        if a.size == 0:
            return
        with self._lock:
            self._chunks.append(a)
            self._n += a.size
            while self._n > self._max and self._chunks:
                self._n -= self._chunks.popleft().size

    def read(self, n: int, latency: int = 0) -> np.ndarray:
        """Aynan n ta sample qaytaradi; yetmasa nol bilan to'ldiradi."""
        out = np.zeros(n, dtype=np.float32)
        with self._lock:
            if not self._primed:
                if self._n >= n + latency:
                    self._primed = True
                else:
                    return out
            pos = 0
            while pos < n and self._chunks:
                c = self._chunks[0]
                take = min(c.size, n - pos)
                out[pos:pos + take] = c[:take]
                if take == c.size:
                    self._chunks.popleft()
                else:
                    self._chunks[0] = c[take:]
                self._n -= take
                pos += take
            if pos < n:           # bufer bo'shab qoldi: keyingi nutq oldidan qayta "isitamiz"
                self._primed = False
        return out

    def trim(self, keep: int) -> None:
        with self._lock:
            while self._n > keep and self._chunks:
                c = self._chunks[0]
                drop = min(c.size, self._n - keep)
                if drop == c.size:
                    self._chunks.popleft()
                else:
                    self._chunks[0] = c[drop:]
                self._n -= drop

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._n = 0
            self._primed = False


class LinearResampler:
    """Oddiy chiziqli resampler (nutq uchun yetarli). Oqim bo'ylab holatni saqlaydi."""

    def __init__(self, in_rate: int, out_rate: int = RATE) -> None:
        self.in_rate = in_rate
        self.out_rate = out_rate
        self.step = in_rate / out_rate
        self._prev: np.ndarray | None = None
        self._pos = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        if x.size == 0:
            return x
        if self.in_rate == self.out_rate:
            return x
        data = x if self._prev is None else np.concatenate([self._prev, x])
        idx_max = data.size - 1
        if idx_max < self._pos:
            self._prev = data[-1:]
            self._pos -= idx_max
            return np.zeros(0, dtype=np.float32)
        n = int((idx_max - self._pos) / self.step) + 1
        p = self._pos + np.arange(n, dtype=np.float64) * self.step
        i0 = np.minimum(p.astype(np.int64), idx_max)
        i1 = np.minimum(i0 + 1, idx_max)
        f = (p - i0).astype(np.float32)
        out = data[i0] * (1.0 - f) + data[i1] * f
        self._pos = self._pos + n * self.step - idx_max
        self._prev = data[-1:]
        return out.astype(np.float32, copy=False)


def to_mono_float(raw, channels: int, dtype) -> np.ndarray:
    a = np.frombuffer(raw, dtype=dtype)
    if channels > 1:
        usable = (a.size // channels) * channels
        a = a[:usable].reshape(-1, channels).mean(axis=1)
    if dtype == np.int16:
        return (a.astype(np.float32) / 32768.0)
    return a.astype(np.float32, copy=False)


# --------------------------------------------------------------------------- WAV

_HEADER = 44


def _wav_header(data_bytes: int, rate: int, channels: int) -> bytes:
    data_bytes = min(data_bytes, 0xFFFFFFFF - 36)
    byte_rate = rate * channels * 2
    return (b"RIFF" + struct.pack("<I", 36 + data_bytes) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, channels, rate, byte_rate, channels * 2, 16) +
            b"data" + struct.pack("<I", data_bytes))


class WavWriter:
    """Qulay WAV yozuvchi: sarlavha vaqti-vaqti bilan yangilanadi, shuning uchun
    dastur uzilib qolsa ham faylni tuzatib (repair_wav) ishlatish mumkin."""

    def __init__(self, path: str | Path, rate: int = RATE, channels: int = 2) -> None:
        self.path = str(path)
        self.rate = rate
        self.channels = channels
        self.bytes = 0
        self._f = open(self.path, "wb")
        self._f.write(_wav_header(0, rate, channels))
        self._last_flush = time.monotonic()

    def write(self, pcm: bytes) -> None:
        self._f.write(pcm)
        self.bytes += len(pcm)
        if time.monotonic() - self._last_flush > 2.0:
            self._update_header()

    def _update_header(self) -> None:
        pos = self._f.tell()
        self._f.seek(0)
        self._f.write(_wav_header(self.bytes, self.rate, self.channels))
        self._f.seek(pos)
        self._f.flush()
        self._last_flush = time.monotonic()

    def close(self) -> None:
        try:
            self._update_header()
        finally:
            self._f.close()

    @property
    def seconds(self) -> float:
        return self.bytes / (self.rate * self.channels * 2)


def repair_wav(path: str | Path, rate: int = RATE, channels: int = 2) -> bool:
    """Uzilib qolgan WAV faylning sarlavhasini haqiqiy hajmga moslab tuzatadi."""
    try:
        p = Path(path)
        size = p.stat().st_size
        if size <= _HEADER:
            return False
        data = size - _HEADER
        data -= data % (channels * 2)
        with open(p, "r+b") as f:
            f.write(_wav_header(data, rate, channels))
            f.truncate(_HEADER + data)
        return True
    except Exception:
        log.exception("WAV ni tuzatib bo'lmadi")
        return False


# --------------------------------------------------------------------------- qurilmalar

def _wasapi_index(sd) -> int | None:
    for i, h in enumerate(sd.query_hostapis()):
        if "WASAPI" in h["name"]:
            return i
    return None


def list_input_devices() -> list[str]:
    """Mikrofon nomlari (WASAPI)."""
    try:
        import sounddevice as sd
        w = _wasapi_index(sd)
        names: list[str] = []
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and (w is None or d["hostapi"] == w):
                if d["name"] not in names:
                    names.append(d["name"])
        return names
    except Exception:
        log.exception("Mikrofonlar ro'yxatini olib bo'lmadi")
        return []


def list_loopback_devices() -> list[str]:
    """Kompyuter ovozini yozib olish mumkin bo'lgan dinamik/quloqchin nomlari."""
    try:
        import pyaudiowpatch as pa
        p = pa.PyAudio()
        try:
            return [d["name"] for d in p.get_loopback_device_info_generator()]
        finally:
            p.terminate()
    except Exception:
        log.exception("Dinamiklar ro'yxatini olib bo'lmadi")
        return []


# --------------------------------------------------------------------------- manbalar

class MicInput:
    """Mikrofon: sounddevice, WASAPI (auto_convert bilan 48 kHz)."""

    def __init__(self, device_name: str, buffer: AudioBuffer) -> None:
        self.device_name = device_name
        self.buffer = buffer
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        w = _wasapi_index(sd)
        device = None
        extra = None
        if w is not None:
            hostapi = sd.query_hostapis(w)
            device = hostapi["default_input_device"]
            if self.device_name:
                for i, d in enumerate(sd.query_devices()):
                    if d["hostapi"] == w and d["max_input_channels"] > 0 and d["name"] == self.device_name:
                        device = i
                        break
            extra = sd.WasapiSettings(auto_convert=True)
        elif self.device_name:
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0 and d["name"] == self.device_name:
                    device = i
                    break
        if device is None or device < 0:
            raise RuntimeError("Mikrofon topilmadi")

        def cb(indata, frames, t, status):  # noqa: ANN001
            if status:
                log.debug("mic status: %s", status)
            a = indata[:, 0] if indata.shape[1] == 1 else indata.mean(axis=1)
            self.buffer.write(np.array(a, dtype=np.float32))

        last_err: Exception | None = None
        for ch in (1, 2):
            try:
                self._stream = sd.InputStream(
                    device=device, channels=ch, samplerate=RATE, dtype="float32",
                    latency="low", callback=cb, extra_settings=extra)
                self._stream.start()
                return
            except Exception as e:  # noqa: BLE001
                last_err = e
                self._stream = None
        raise RuntimeError(f"Mikrofonni ochib bo'lmadi: {last_err}")

    def stop(self) -> None:
        s, self._stream = self._stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                log.exception("Mikrofonni yopishda xato")


class LoopbackInput:
    """Kompyuterdan chiqayotgan ovoz (WASAPI loopback)."""

    def __init__(self, device_name: str, buffer: AudioBuffer) -> None:
        self.device_name = device_name
        self.buffer = buffer
        self._pa = None
        self._stream = None
        self._resampler: LinearResampler | None = None
        self._channels = 2
        self._opened_name = ""
        self._watch_stop = threading.Event()
        self._watch_thread: threading.Thread | None = None

    # -- qurilmani tanlash
    @staticmethod
    def _default_output_name() -> str:
        import pyaudiowpatch as pa
        p = pa.PyAudio()
        try:
            wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
            return p.get_device_info_by_index(wasapi["defaultOutputDevice"])["name"]
        finally:
            p.terminate()

    def _open(self) -> None:
        import pyaudiowpatch as pa

        p = pa.PyAudio()
        try:
            wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
            target = None
            if self.device_name:
                for lb in p.get_loopback_device_info_generator():
                    if lb["name"] == self.device_name:
                        target = lb
                        break
            if target is None:
                default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
                if default_out.get("isLoopbackDevice"):
                    target = default_out
                else:
                    for lb in p.get_loopback_device_info_generator():
                        if default_out["name"] in lb["name"]:
                            target = lb
                            break
            if target is None:
                raise RuntimeError("Dinamik (loopback) qurilmasi topilmadi")

            self._channels = max(1, int(target["maxInputChannels"]))
            rate = int(target["defaultSampleRate"])
            self._resampler = LinearResampler(rate, RATE)
            self._opened_name = self._default_name_from(target)

            def cb(in_data, frame_count, time_info, status):  # noqa: ANN001
                try:
                    mono = to_mono_float(in_data, self._channels, np.int16)
                    r = self._resampler
                    if r is not None:
                        mono = r.process(mono)
                    self.buffer.write(mono)
                except Exception:
                    log.exception("loopback callback")
                return (None, pa.paContinue)

            self._stream = p.open(
                format=pa.paInt16, channels=self._channels, rate=rate, input=True,
                input_device_index=target["index"], frames_per_buffer=int(rate * 0.02),
                stream_callback=cb)
            self._pa = p
        except Exception:
            p.terminate()
            raise

    @staticmethod
    def _default_name_from(target: dict) -> str:
        return str(target.get("name", ""))

    def start(self) -> None:
        self._open()
        if not self.device_name:
            self._watch_stop.clear()
            self._watch_thread = threading.Thread(target=self._watch_default, daemon=True,
                                                  name="loopback-watch")
            self._watch_thread.start()

    def _close_stream(self) -> None:
        s, self._stream = self._stream, None
        p, self._pa = self._pa, None
        try:
            if s is not None:
                s.stop_stream()
                s.close()
        except Exception:
            log.exception("Loopback oqimini yopishda xato")
        try:
            if p is not None:
                p.terminate()
        except Exception:
            pass

    def _watch_default(self) -> None:
        """Quloqchin ulanganda/uzilganda standart dinamik o'zgaradi — shunda qayta ulanamiz."""
        while not self._watch_stop.wait(3.0):
            try:
                cur = self._default_output_name()
                if cur and cur not in self._opened_name and self._opened_name not in cur:
                    log.info("Standart dinamik o'zgardi: %s -> %s", self._opened_name, cur)
                    self._close_stream()
                    self.buffer.clear()
                    self._open()
            except Exception:
                log.exception("Dinamik kuzatuvchisi xatosi")

    def stop(self) -> None:
        self._watch_stop.set()
        t = self._watch_thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=2.0)
        self._close_stream()


# --------------------------------------------------------------------------- dvigatel

class AudioEngine:
    """Doimiy ishlab turadi (indikatorlar yozuvdan oldin ham ko'rinishi uchun).
    start_recording() chaqirilganda aralashtirilgan ovoz WAV ga yoziladi."""

    def __init__(self) -> None:
        self.mic_buf = AudioBuffer()
        self.loop_buf = AudioBuffer()
        self.mic_meter = LevelMeter()
        self.loop_meter = LevelMeter()
        self.mic_muted = False
        self.loop_muted = False
        self.mic_error = ""
        self.loop_error = ""
        self._mic = None
        self._loop = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._rec_lock = threading.Lock()
        self._wav: WavWriter | None = None
        self._paused = False
        self._mic_name = ""
        self._loop_name = ""
        self.last_rms_mix = 0.0

    # -- manbalarni ochish (testlarda almashtiriladi)
    def _make_mic(self, name: str):
        return MicInput(name, self.mic_buf)

    def _make_loop(self, name: str):
        return LoopbackInput(name, self.loop_buf)

    def _open_sources(self) -> None:
        self.mic_error = ""
        self.loop_error = ""
        try:
            self._mic = self._make_mic(self._mic_name)
            self._mic.start()
        except Exception as e:  # noqa: BLE001
            log.warning("Mikrofon ochilmadi: %s", e)
            self.mic_error = str(e) or "Mikrofon ochilmadi"
            self._mic = None
        try:
            self._loop = self._make_loop(self._loop_name)
            self._loop.start()
        except Exception as e:  # noqa: BLE001
            log.warning("Dinamik ochilmadi: %s", e)
            self.loop_error = str(e) or "Dinamik ochilmadi"
            self._loop = None
        self.mic_meter.reset_silence()
        self.loop_meter.reset_silence()

    def _close_sources(self) -> None:
        for src in (self._mic, self._loop):
            if src is not None:
                try:
                    src.stop()
                except Exception:
                    log.exception("Manbani yopishda xato")
        self._mic = None
        self._loop = None
        self.mic_buf.clear()
        self.loop_buf.clear()

    def start(self, mic_name: str = "", loop_name: str = "") -> None:
        if self._thread is not None:
            return
        self._mic_name = mic_name
        self._loop_name = loop_name
        self._open_sources()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="audio-mixer")
        self._thread.start()

    def restart_sources(self, mic_name: str, loop_name: str) -> None:
        """Qurilma o'zgarganda (faqat yozuv bo'lmaganda chaqiriladi)."""
        self._mic_name = mic_name
        self._loop_name = loop_name
        self._close_sources()
        self._open_sources()

    def stop(self) -> None:
        self._stop.set()
        t, self._thread = self._thread, None
        if t is not None:
            t.join(timeout=3.0)
        self.stop_recording()
        self._close_sources()

    # -- yozuv
    def start_recording(self, wav_path: str | Path) -> None:
        with self._rec_lock:
            self._wav = WavWriter(wav_path)
            self._paused = False

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop_recording(self) -> float:
        """WAV ni yopadi, yozilgan davomiylikni (soniya) qaytaradi."""
        with self._rec_lock:
            w, self._wav = self._wav, None
        if w is None:
            return 0.0
        w.close()
        return w.seconds

    @property
    def recording(self) -> bool:
        return self._wav is not None

    # -- indikatorlar
    def levels(self) -> tuple[float, float]:
        return self.mic_meter.value(), self.loop_meter.value()

    def mic_available(self) -> bool:
        return self._mic is not None

    def loop_available(self) -> bool:
        return self._loop is not None

    # -- aralashtirgich oqimi
    def _run(self) -> None:
        lat = int(PRIME_LATENCY * RATE)
        backlog = int(MAX_BACKLOG * RATE)
        t0 = time.monotonic()
        drained = 0
        min_n = int(TICK * RATE * 0.5)
        while not self._stop.is_set():
            try:
                target = int((time.monotonic() - t0) * RATE)
                n = target - drained
                if n < min_n:
                    time.sleep(0.005)
                    continue
                n = min(n, RATE)
                drained += n

                mic = self.mic_buf.read(n, lat)
                loop = self.loop_buf.read(n, lat)
                if self.mic_buf.available > backlog:
                    self.mic_buf.trim(int(0.05 * RATE))
                if self.loop_buf.available > backlog:
                    self.loop_buf.trim(int(0.05 * RATE))

                if self.mic_muted or self._mic is None:
                    mic = np.zeros(n, dtype=np.float32)
                if self.loop_muted or self._loop is None:
                    loop = np.zeros(n, dtype=np.float32)
                self.mic_meter.update_level(block_level(mic))
                self.loop_meter.update_level(block_level(loop))

                with self._rec_lock:
                    w = self._wav
                    if w is not None and not self._paused:
                        mix = np.clip(mic + loop, -1.0, 1.0)
                        pcm = (mix * 32767.0).astype(np.int16)
                        stereo = np.empty((n, 2), dtype=np.int16)
                        stereo[:, 0] = pcm
                        stereo[:, 1] = pcm
                        w.write(stereo.tobytes())
            except Exception:
                log.exception("Aralashtirgich xatosi")
                time.sleep(0.05)
