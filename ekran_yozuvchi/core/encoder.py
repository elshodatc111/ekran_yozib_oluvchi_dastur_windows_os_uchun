"""FFmpeg bilan ishlash: kodlovchini aniqlash, video kodlash jarayoni, yakuniy birlashtirish (mux)."""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from typing import Callable

from . import winutil
from .profiles import Profile

log = logging.getLogger(__name__)

HW_ENCODERS = ["h264_nvenc", "h264_qsv", "h264_amf"]
ENCODER_TITLES = {
    "h264_nvenc": "NVIDIA NVENC (video karta)",
    "h264_qsv": "Intel Quick Sync (video karta)",
    "h264_amf": "AMD AMF (video karta)",
    "libx264": "Protsessor (x264)",
}


def encoder_title(name: str) -> str:
    return ENCODER_TITLES.get(name, name)


def _run(cmd: list[str], timeout: float) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, **winutil.subprocess_kwargs())
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:  # noqa: BLE001
        return -2, str(e)


def probe_encoder(ffmpeg: str) -> str:
    """Ishlaydigan eng yaxshi H.264 kodlovchini topadi (har birini 10 kadr bilan sinaydi)."""
    rc, out = _run([ffmpeg, "-hide_banner", "-encoders"], 15)
    if rc != 0:
        return "libx264"
    for enc in HW_ENCODERS:
        if enc not in out:
            continue
        fmt = "nv12" if enc == "h264_qsv" else "yuv420p"
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
               "-i", "testsrc2=size=1280x720:rate=30", "-frames:v", "10",
               "-vf", f"format={fmt}", "-c:v", enc, "-f", "null", "-"]
        rc, msg = _run(cmd, 20)
        log.info("Kodlovchi sinovi %s -> rc=%s %s", enc, rc, msg.strip()[:200])
        if rc == 0:
            return enc
    return "libx264"


def video_codec_args(profile: Profile, encoder: str) -> list[str]:
    g = str(profile.fps * 2)
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p4", "-rc", "vbr", "-cq", str(profile.cq),
                "-b:v", "0", "-maxrate", profile.maxrate, "-bufsize", profile.bufsize,
                "-bf", "0", "-g", g]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-preset", "medium", "-global_quality", str(profile.cq),
                "-maxrate", profile.maxrate, "-bufsize", profile.bufsize, "-bf", "0", "-g", g]
    if encoder == "h264_amf":
        return ["-c:v", encoder, "-quality", "speed", "-rc", "cqp",
                "-qp_i", str(profile.cq), "-qp_p", str(profile.cq), "-bf", "0", "-g", g]
    return ["-c:v", "libx264", "-preset", profile.x264_preset, "-crf", str(profile.crf),
            "-maxrate", profile.maxrate, "-bufsize", profile.bufsize,
            "-g", g, "-sc_threshold", "0"]


def build_encode_cmd(ffmpeg: str, encoder: str, profile: Profile, src_w: int, src_h: int,
                     out_w: int, out_h: int, out_path: str, pix_fmt: str = "bgra") -> list[str]:
    target_fmt = "nv12" if encoder == "h264_qsv" else "yuv420p"
    vf = f"scale={out_w}:{out_h}:flags=fast_bilinear:out_color_matrix=bt709:out_range=tv,format={target_fmt}"
    return ([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "rawvideo", "-pix_fmt", pix_fmt, "-video_size", f"{src_w}x{src_h}",
             "-framerate", str(profile.fps), "-i", "pipe:0", "-an", "-vf", vf]
            + video_codec_args(profile, encoder)
            + ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
               "-flush_packets", "1", "-f", "matroska", out_path])


class VideoEncoder:
    """FFmpeg jarayoni: xom kadrlar stdin orqali beriladi, video.mkv ga yoziladi."""

    def __init__(self, cmd: list[str], log_path: str) -> None:
        self.cmd = cmd
        self.log_path = log_path
        self.proc: subprocess.Popen | None = None
        self._log_f = None

    def start(self) -> None:
        self._log_f = open(self.log_path, "wb")
        self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=self._log_f, **winutil.subprocess_kwargs())

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def write(self, data) -> None:
        assert self.proc is not None and self.proc.stdin is not None
        self.proc.stdin.write(data)

    def error_text(self) -> str:
        try:
            if self._log_f:
                self._log_f.flush()
            return Path(self.log_path).read_text(encoding="utf-8", errors="replace")[-600:].strip()
        except Exception:
            return ""

    def close(self, timeout: float = 120.0) -> int:
        p = self.proc
        if p is None:
            return -1
        try:
            if p.stdin:
                p.stdin.close()
        except Exception:
            pass
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
        if self._log_f:
            try:
                self._log_f.close()
            except Exception:
                pass
        return p.returncode if p.returncode is not None else -1


def mux(ffmpeg: str, video: str, audio: str | None, out_path: str, duration: float,
        progress_cb: Callable[[float], None] | None = None,
        log_path: str | None = None) -> tuple[bool, str]:
    """video.mkv (+ audio.wav) -> MP4 (H.264 nusxalanadi, ovoz AAC). Qaytaradi: (muvaffaqiyat, xabar)."""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-nostats", "-progress", "pipe:1",
           "-i", video]
    if audio:
        cmd += ["-i", audio, "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-map", "0:v:0", "-c:v", "copy"]
    cmd += ["-movflags", "+faststart", out_path]

    err_path = log_path or (out_path + ".log")
    try:
        with open(err_path, "wb") as errf:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf,
                                 **winutil.subprocess_kwargs())
            assert p.stdout is not None
            for raw in p.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    try:
                        us = int(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    if progress_cb and duration > 0:
                        progress_cb(max(0.0, min(0.99, us / 1_000_000 / duration)))
            p.stdout.close()
            p.wait()
        ok = p.returncode == 0 and Path(out_path).is_file() and Path(out_path).stat().st_size > 0
        if ok:
            if progress_cb:
                progress_cb(1.0)
            try:
                Path(err_path).unlink()
            except Exception:
                pass
            return True, ""
        msg = Path(err_path).read_text(encoding="utf-8", errors="replace")[-600:].strip()
        return False, msg or f"ffmpeg kodi {p.returncode}"
    except Exception as e:  # noqa: BLE001
        log.exception("mux xatosi")
        return False, str(e)


def run_in_thread(fn, *args, name: str = "worker") -> threading.Thread:
    t = threading.Thread(target=fn, args=args, daemon=True, name=name)
    t.start()
    return t
