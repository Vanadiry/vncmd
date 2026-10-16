import hashlib
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
    # 畸形输入会让 ffprobe 挂住不返回，cmd_check 的线程池里挂一个就少一个 worker
    try:
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
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    fmt = data.get("format") or {}
    duration = _to_float(fmt.get("duration"))
    if duration is None:
        for stream in data.get("streams") or []:
            duration = _to_float(stream.get("duration"))
            if duration is not None:
                break
    return {"duration": duration, "bitrate": _to_int(fmt.get("bit_rate"))}


def ffmpeg_decode(path: str) -> tuple[list[str], float | None]:
    try:
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
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], None
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
    try:
        proc = subprocess.run(
            ["flac", "-t", "-s", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "flac 校验超时"
    except OSError as e:
        return f"无法运行 flac：{e}"
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or "").strip()
    return None


def _short_digest(digest: str, n: int = 7) -> str:
    """摘要只留前几位，md5 有雪崩效应，一旦不符开头必然不同，全长只是噪音"""
    return digest if len(digest) <= n else digest[:n] + "..."


def check_md5(path: str, expect_md5: str, expect_size: int = 0) -> tuple[bool, str]:
    """比对服务端声明的大小与 md5，返回 (是否通过, 说明)

    md5 是唯一的裁决者：只要 md5 对得上就放行，哪怕 size 字段本身不准，
    否则一次字段错乱就会拒掉完好文件。size 用来在 md5 缺席时兜底，
    并在报错里补上最有诊断价值的那条线索。
    """
    if not expect_md5 and not expect_size:
        return True, ""

    actual_size = Path(path).stat().st_size
    size_bad = bool(expect_size) and actual_size != expect_size

    if not expect_md5:
        if size_bad:
            return False, f"大小不符 (声明 {expect_size} 实际 {actual_size})"
        return True, ""

    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    actual = h.hexdigest()
    if actual == expect_md5.lower():
        return True, ""

    # 截断是下载最常见的坏法，此时大小差异比摘要更能说明问题
    if size_bad:
        return False, (
            f"大小不符 (声明 {expect_size} 实际 {actual_size})，"
            f"md5 也不符 ({_short_digest(expect_md5)} 对 {_short_digest(actual)})"
        )
    return (
        False,
        f"md5 不符 (声明 {_short_digest(expect_md5)} 实际 {_short_digest(actual)})",
    )


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
