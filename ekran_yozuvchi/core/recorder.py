"""Yozuv boshqaruvchisi: holatlar (IDLE/RECORDING/PAUSED/SAVING), video oqimi, saqlash."""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from .. import paths
from ..config import Config
from . import disk, winutil
from .audio_capture import AudioEngine, repair_wav
from .encoder import VideoEncoder, build_encode_cmd, encoder_title, mux, probe_encoder
from .profiles import compute_output_size, resolve_profile
from .video_capture import CursorPainter, ScreenGrabber

log = logging.getLogger(__name__)


class State(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    SAVING = "saving"


class ActiveClock:
    """Faol yozuv vaqti (pauza hisobga olinmaydi)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._acc = 0.0
        self._t0: float | None = None
        self.started = False

    def start(self) -> None:
        with self._lock:
            self._acc = 0.0
            self._t0 = time.monotonic()
            self.started = True

    def pause(self) -> None:
        with self._lock:
            if self._t0 is not None:
                self._acc += time.monotonic() - self._t0
                self._t0 = None

    def resume(self) -> None:
        with self._lock:
            if self._t0 is None and self.started:
                self._t0 = time.monotonic()

    stop = pause

    @property
    def running(self) -> bool:
        return self._t0 is not None

    def elapsed(self) -> float:
        with self._lock:
            return self._acc + ((time.monotonic() - self._t0) if self._t0 is not None else 0.0)


class VideoWorker(threading.Thread):
    """Ekrandan kadr oladi, kursor chizadi, FFmpeg'ga yuboradi (CFR: kerak bo'lsa kadr takrorlanadi)."""

    def __init__(self, grabber_factory: Callable[[int], ScreenGrabber], monitor_index: int,
                 profile_key: str, encoder_chain: list[str], ffmpeg: str, video_path: str,
                 log_path: str, clock: ActiveClock, show_cursor: bool,
                 on_fatal: Callable[[str], None]) -> None:
        super().__init__(daemon=True, name="video-worker")
        self.grabber_factory = grabber_factory
        self.monitor_index = monitor_index
        self.profile_key = profile_key
        self.encoder_chain = encoder_chain
        self.ffmpeg = ffmpeg
        self.video_path = video_path
        self.log_path = log_path
        self.clock = clock
        self.show_cursor = show_cursor
        self.on_fatal = on_fatal

        self.ready = threading.Event()
        self.go = threading.Event()
        self.stop_event = threading.Event()
        self.start_error = ""
        self.used_encoder = ""
        self.profile = None
        self.size = (0, 0)
        self.frames_written = 0
        self.late = 0
        self.total = 0
        self._enc: VideoEncoder | None = None

    # -- tayyorlash
    def _start_encoder(self, grabber: ScreenGrabber, width: int, height: int) -> None:
        errors: list[str] = []
        for enc_name in self.encoder_chain:
            profile = resolve_profile(self.profile_key, enc_name)
            ow, oh = compute_output_size(width, height, profile.max_height)
            cmd = build_encode_cmd(self.ffmpeg, enc_name, profile, width, height, ow, oh, self.video_path)
            enc = VideoEncoder(cmd, self.log_path)
            try:
                enc.start()
                time.sleep(0.5)
                if enc.alive():
                    self._enc = enc
                    self.used_encoder = enc_name
                    self.profile = profile
                    self.size = (ow, oh)
                    return
                errors.append(f"{enc_name}: {enc.error_text()}")
                log.warning("Kodlovchi %s ishga tushmadi: %s", enc_name, enc.error_text())
                enc.close(5)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{enc_name}: {e}")
                log.exception("Kodlovchini ishga tushirib bo'lmadi: %s", enc_name)
        raise RuntimeError("Video kodlovchi ishga tushmadi. " + " | ".join(errors)[-300:])

    # -- asosiy sikl
    def run(self) -> None:
        grabber: ScreenGrabber | None = None
        try:
            try:
                grabber = self.grabber_factory(self.monitor_index)
                grabber.open()
                base = grabber.first_frame()
                h, w = base.shape[:2]
                self._start_encoder(grabber, w, h)
            except Exception as e:  # noqa: BLE001
                log.exception("Video tayyorlashda xato")
                self.start_error = str(e)
                return
            finally:
                self.ready.set()

            if not self.go.wait(20) or self.stop_event.is_set():
                return
            assert self._enc is not None and self.profile is not None
            self._loop(grabber, base)
        except Exception as e:  # noqa: BLE001
            log.exception("Video oqimi to'xtadi")
            self.on_fatal(f"Video yozishda xato: {e}")
        finally:
            if self._enc is not None:
                self._enc.close()
            if grabber is not None:
                grabber.close()

    def _loop(self, grabber: ScreenGrabber, base) -> None:
        fps = self.profile.fps
        painter = CursorPainter(max(1.0, base.shape[0] / 1080.0)) if self.show_cursor else None
        written = 0
        enc = self._enc
        clock = self.clock
        while not self.stop_event.is_set():
            if not clock.running:
                time.sleep(0.02)
                continue
            elapsed = clock.elapsed()
            due = (written + 1) / fps
            if elapsed < due:
                time.sleep(min(due - elapsed, 0.02))
                continue
            if not enc.alive():
                self.on_fatal("Kodlovchi kutilmaganda to'xtadi: " + enc.error_text()[-200:])
                return
            frame = grabber.grab()
            if frame is not None:
                base = frame
            expected = int(clock.elapsed() * fps)
            behind = max(1, expected - written)
            self.total += 1
            if behind >= 2:
                self.late += 1
            saved = None
            if painter is not None:
                pos = winutil.get_cursor_pos()
                if pos is not None:
                    saved = painter.draw(base, pos[0] - grabber.left, pos[1] - grabber.top)
            try:
                view = memoryview(base).cast("B") if base.flags["C_CONTIGUOUS"] else base.tobytes()
                for _ in range(behind):
                    enc.write(view)
            except (BrokenPipeError, OSError, ValueError) as e:
                self.on_fatal(f"FFmpeg'ga yozib bo'lmadi (disk to'lgan bo'lishi mumkin): {e}")
                return
            finally:
                if painter is not None:
                    CursorPainter.restore(base, saved)
            written += behind
            self.frames_written = written

    def stop(self) -> None:
        self.stop_event.set()
        self.go.set()


class Recorder(QObject):
    state_changed = Signal(str)
    saved = Signal(str)
    error = Signal(str)
    notice = Signal(str)
    progress = Signal(float)
    encoder_ready = Signal(str)
    _fatal = Signal(str)

    def __init__(self, config: Config, audio: AudioEngine, ffmpeg: str | None = None,
                 grabber_factory: Callable[[int], ScreenGrabber] | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.audio = audio
        self._ffmpeg = ffmpeg
        self._grabber_factory = grabber_factory or (lambda idx: ScreenGrabber(idx))
        self.state = State.IDLE
        self.clock = ActiveClock()
        self.encoder_name = ""
        self._probe_thread: threading.Thread | None = None
        self._worker: VideoWorker | None = None
        self._out_dir: Path | None = None
        self._tmp_dir: Path | None = None
        self._name = ""
        self._final_path: Path | None = None
        self._video_path = ""
        self._warned_space = False
        self._warned_late = False
        self._duration = 0.0
        self.save_progress = 0.0
        self._fatal.connect(self._on_fatal)
        self.state_changed.connect(self._apply_sleep)

    # ------------------------------------------------------------------ yordamchi
    @property
    def ffmpeg(self) -> str | None:
        if self._ffmpeg is None:
            self._ffmpeg = paths.find_ffmpeg()
        return self._ffmpeg

    def output_dir(self) -> Path:
        d = (self.config["output_dir"] or "").strip()
        return Path(d) if d else disk.default_output_dir()

    def _set_state(self, st: State) -> None:
        self.state = st
        self.state_changed.emit(st.value)

    def _apply_sleep(self, st: str) -> None:
        winutil.prevent_sleep(st in (State.RECORDING.value, State.PAUSED.value))

    def elapsed(self) -> float:
        return self._duration if self.state == State.SAVING else self.clock.elapsed()

    # ------------------------------------------------------------------ kodlovchini aniqlash
    def probe_async(self) -> None:
        if self._probe_thread is not None or not self.ffmpeg:
            return

        def work() -> None:
            name = probe_encoder(self.ffmpeg)  # type: ignore[arg-type]
            self.encoder_name = name
            log.info("Tanlangan kodlovchi: %s", name)
            self.encoder_ready.emit(name)

        self._probe_thread = threading.Thread(target=work, daemon=True, name="encoder-probe")
        self._probe_thread.start()

    def _encoder_chain(self) -> list[str]:
        if self.config["encoder_mode"] == "cpu":
            return ["libx264"]
        t = self._probe_thread
        if t is not None and t.is_alive():
            t.join(20)
        if not self.encoder_name and self.ffmpeg:
            self.encoder_name = probe_encoder(self.ffmpeg)
        name = self.encoder_name or "libx264"
        return [name] if name == "libx264" else [name, "libx264"]

    # ------------------------------------------------------------------ boshlash
    def start(self) -> bool:
        if self.state != State.IDLE:
            return False
        if not self.ffmpeg:
            self.error.emit("ffmpeg.exe topilmadi. Uni dastur papkasidagi «ffmpeg» papkasiga joylang "
                            "(get_ffmpeg.ps1 faylini ishga tushiring).")
            return False
        out_dir = self.output_dir()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Saqlash papkasini yaratib bo'lmadi: {out_dir}\n{e}")
            return False
        if winutil.is_fat32(str(out_dir)):
            self.error.emit("Bu disk FAT32 formatida: 4 GB dan katta fayl yozib bo'lmaydi. "
                            "Sozlamalardan boshqa (NTFS) diskdagi papkani tanlang.")
            return False
        free = disk.free_bytes(out_dir)
        if free < disk.MIN_FREE_TO_START:
            self.error.emit(f"Diskda bo'sh joy yetarli emas ({disk.format_size(free)}). "
                            "Eski videolarni o'chiring yoki boshqa papka tanlang.")
            return False

        name = disk.make_recording_name(self.config["lesson_name"])
        tmp_dir = out_dir / disk.TEMP_DIR_NAME / name
        try:
            tmp_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Vaqtinchalik papka yaratilmadi: {e}")
            return False

        video_path = str(tmp_dir / "video.mkv")
        wav_path = str(tmp_dir / "audio.wav")
        self.clock = ActiveClock()
        worker = VideoWorker(
            self._grabber_factory, int(self.config["monitor_index"] or 0), self.config["profile"],
            self._encoder_chain(), self.ffmpeg, video_path, str(tmp_dir / "ffmpeg_video.log"),
            self.clock, bool(self.config["show_cursor"]), self._fatal.emit)
        worker.start()
        worker.ready.wait(30)
        if not worker.ready.is_set() or worker.start_error or worker.profile is None:
            msg = worker.start_error or "Video tayyor bo'lmadi"
            worker.stop()
            self._discard_tmp(tmp_dir, out_dir)
            self.error.emit("Yozishni boshlab bo'lmadi: " + msg)
            return False

        try:
            self.audio.start_recording(wav_path)
        except Exception as e:  # noqa: BLE001
            worker.stop()
            self._discard_tmp(tmp_dir, out_dir)
            self.error.emit(f"Ovoz faylini yaratib bo'lmadi: {e}")
            return False

        self._worker = worker
        self._out_dir = out_dir
        self._tmp_dir = tmp_dir
        self._name = name
        self._video_path = video_path
        self._warned_space = False
        self._warned_late = False
        self._duration = 0.0
        self.save_progress = 0.0
        self.clock.start()
        worker.go.set()
        self._set_state(State.RECORDING)

        if worker.used_encoder != (self._encoder_chain()[0]):
            self.notice.emit("Video karta kodlovchisi ishlamadi, protsessor bilan yozilmoqda.")
        if free < disk.WARN_FREE:
            self._warned_space = True
            self.notice.emit(f"Diskda bo'sh joy kam: {disk.format_size(free)}.")
        return True

    # ------------------------------------------------------------------ pauza
    def toggle_pause(self) -> None:
        if self.state == State.RECORDING:
            self.clock.pause()
            self.audio.pause()
            self._set_state(State.PAUSED)
        elif self.state == State.PAUSED:
            self.clock.resume()
            self.audio.resume()
            self._set_state(State.RECORDING)

    # ------------------------------------------------------------------ to'xtatish
    def stop(self) -> None:
        if self.state not in (State.RECORDING, State.PAUSED):
            return
        self.clock.stop()
        self._duration = self.clock.elapsed()
        self.save_progress = 0.0
        self._set_state(State.SAVING)
        threading.Thread(target=self._finalize, daemon=True, name="finalize").start()

    def _finalize(self) -> None:
        worker = self._worker
        tmp_dir, out_dir = self._tmp_dir, self._out_dir
        assert worker is not None and tmp_dir is not None and out_dir is not None
        try:
            worker.stop()
            worker.join(120)
            self.audio.stop_recording()
            if worker.frames_written == 0:
                self.error.emit("Video yozilmadi (kadrlar olinmadi). Vaqtinchalik fayllar saqlandi:\n"
                                + str(tmp_dir))
                return
            wav = tmp_dir / "audio.wav"
            audio_arg = str(wav) if wav.is_file() and wav.stat().st_size > 44 else None
            final = disk.unique_path(out_dir, self._name)
            ok, msg = mux(self.ffmpeg, self._video_path, audio_arg, str(final), self._duration,  # type: ignore[arg-type]
                          lambda p: self._emit_progress(p), str(tmp_dir / "ffmpeg_mux.log"))
            if ok:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                disk.cleanup_temp_root(out_dir)
                self.saved.emit(str(final))
            else:
                self.error.emit("Videoni saqlashda xato. Xom fayllar saqlandi:\n" + str(tmp_dir)
                                + "\n" + msg[-200:])
        except Exception as e:  # noqa: BLE001
            log.exception("Saqlashda xato")
            self.error.emit(f"Saqlashda xato: {e}")
        finally:
            self._worker = None
            self._set_state(State.IDLE)

    def _emit_progress(self, p: float) -> None:
        self.save_progress = p
        self.progress.emit(p)

    def _on_fatal(self, msg: str) -> None:
        if self.state in (State.RECORDING, State.PAUSED):
            self.error.emit(msg + "\nHozirgacha yozilgan qismi saqlanadi.")
            self.stop()

    def _discard_tmp(self, tmp_dir: Path, out_dir: Path) -> None:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        disk.cleanup_temp_root(out_dir)

    # ------------------------------------------------------------------ holat
    def status(self) -> dict:
        size = 0
        try:
            if self._video_path and self.state in (State.RECORDING, State.PAUSED):
                size = os.path.getsize(self._video_path)
                wav = os.path.join(os.path.dirname(self._video_path), "audio.wav")
                if os.path.exists(wav):
                    size += os.path.getsize(wav)
        except OSError:
            pass
        out = self._out_dir or self.output_dir()
        return {"elapsed": self.elapsed(), "size": size, "free": disk.free_bytes(out)}

    def tick(self) -> None:
        """Har soniyada chaqiriladi: disk va yuklama nazorati."""
        if self.state not in (State.RECORDING, State.PAUSED) or self._out_dir is None:
            return
        free = disk.free_bytes(self._out_dir)
        if free < disk.CRITICAL_FREE:
            self.error.emit("Diskda joy tugadi. Yozuv to'xtatildi va hozirgacha yozilgani saqlanadi.")
            self.stop()
            return
        if free < disk.WARN_FREE and not self._warned_space:
            self._warned_space = True
            self.notice.emit(f"Diskda bo'sh joy kam qoldi: {disk.format_size(free)}.")
        w = self._worker
        if w is not None and not self._warned_late and w.total >= 120 and w.profile is not None:
            if w.late / w.total > 0.10 and w.profile.key != "yengil":
                self._warned_late = True
                self.notice.emit("Kompyuter zo'riqmoqda. Sozlamalardan «Yengil» profilni tanlang.")

    # ------------------------------------------------------------------ tiklash
    def recover_orphans(self) -> None:
        """Oldingi uzilgan (kutilmagan o'chish) yozuvlarni topib, videoga aylantiradi."""
        if self.state != State.IDLE or not self.ffmpeg:
            return
        root = self.output_dir() / disk.TEMP_DIR_NAME
        if not root.is_dir():
            return

        def work() -> None:
            recovered = 0
            for d in sorted(root.iterdir()):
                v = d / "video.mkv"
                if not d.is_dir() or not v.is_file() or v.stat().st_size < 1024:
                    continue
                if self.state != State.IDLE:
                    return
                wav = d / "audio.wav"
                audio_arg = None
                if wav.is_file() and repair_wav(wav):
                    audio_arg = str(wav)
                final = disk.unique_path(root.parent, "tiklangan_" + d.name)
                ok, msg = mux(self.ffmpeg, str(v), audio_arg, str(final), 0.0, None,  # type: ignore[arg-type]
                              str(d / "ffmpeg_recover.log"))
                if ok:
                    shutil.rmtree(d, ignore_errors=True)
                    recovered += 1
                else:
                    log.warning("Tiklab bo'lmadi %s: %s", d, msg)
            disk.cleanup_temp_root(root.parent)
            if recovered:
                self.notice.emit(f"Oldingi uzilgan {recovered} ta yozuv tiklandi («tiklangan_...» fayllari).")

        threading.Thread(target=work, daemon=True, name="recover").start()

    def encoder_label(self) -> str:
        if self.config["encoder_mode"] == "cpu":
            return encoder_title("libx264")
        return encoder_title(self.encoder_name) if self.encoder_name else "aniqlanmoqda..."
