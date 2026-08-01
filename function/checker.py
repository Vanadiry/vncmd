import json
import re
import shutil
import subprocess
from pathlib import Path

DURATION_TOL = 1.0

_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def has_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def has_flac() -> bool:
    return bool(shutil.which("flac"))


def ffprobe_info(path: str) -> dict | None:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,bit_rate:stream=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    data = json.loads(proc.stdout)
    fmt = data.get("format") or {}
    duration = _to_float(fmt.get("duration"))
    if duration is None:
        for stream in data.get("streams") or []:
            duration = _to_float(stream.get("duration"))
            if duration is not None:
                break
    return {"duration": duration, "bitrate": _to_int(fmt.get("bit_rate"))}


def ffmpeg_decode(path: str) -> tuple[list[str], float | None]:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-stats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    errors: list[str] = []
    max_time: float | None = None
    for line in proc.stderr.splitlines():
        if not line.strip():
            continue
        match = _TIME_RE.search(line)
        if match:
            h, m, s = match.groups()
            t = int(h) * 3600 + int(m) * 60 + float(s)
            if max_time is None or t > max_time:
                max_time = t
        else:
            errors.append(line.strip())
    if proc.returncode != 0:
        errors.append(f"ffmpeg 退出码 {proc.returncode}")
    return errors, max_time


def flac_test(path: str) -> str | None:
    if not shutil.which("flac"):
        return None
    proc = subprocess.run(
        ["flac", "-t", "-s", str(path)], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or "").strip()
    return None


def check_audio(path: str) -> tuple[bool, str]:
    """Check audio file integrity. Returns (ok, message)."""
    info = ffprobe_info(path)
    declared = info["duration"] if info else None

    errors, actual = ffmpeg_decode(path)
    if errors:
        note = " | ".join(errors[:3])
        if declared and actual is not None and actual >= declared - DURATION_TOL:
            return True, f"解码完整但尾部有异常数据: {note}"
        return False, f"解码出错: {note}"

    if Path(path).suffix.lower() == ".flac":
        err = flac_test(path)
        if err:
            return False, f"flac 无损校验失败: {err}"

    if declared and actual is not None and actual < declared - DURATION_TOL:
        return False, f"疑似截断 (声明 {declared:.0f}s 实际 {actual:.0f}s)"

    return True, ""
