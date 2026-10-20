import hashlib
import json
import re
import shutil
import subprocess
from functools import lru_cache
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


# 缓存 PATH 探测，改 PATH 后需清缓存
@lru_cache(maxsize=1)
def has_ffprobe() -> bool:
    return bool(shutil.which("ffprobe"))


@lru_cache(maxsize=1)
def has_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg"))


@lru_cache(maxsize=1)
def has_flac() -> bool:
    return bool(shutil.which("flac"))


# 三样工具各管一段校验，探测函数与说明同表维护
CHECK_TOOLS = {
    "ffprobe": (has_ffprobe, "时长交叉验证"),
    "ffmpeg": (has_ffmpeg, "全量解码"),
    "flac": (has_flac, "flac CRC 校验"),
}


def check_tools() -> dict[str, bool]:
    """三样校验工具的可用情况，启动检查与任务开始时的提示共用一份"""
    return {name: probe() for name, (probe, _role) in CHECK_TOOLS.items()}


def any_check_tool() -> bool:
    """三样里是否有一样能真正校验，ffprobe 不算"""
    tools = check_tools()
    return tools["ffmpeg"] or tools["flac"]


def missing_check_tools() -> list[str]:
    available = check_tools()
    return [name for name in CHECK_TOOLS if not available[name]]


def describe_missing_check_tools() -> str:
    """缺哪些校验工具以及因此少做哪几步，三样都在时返回空串"""
    missing = missing_check_tools()
    if not missing:
        return ""
    roles = "、".join(CHECK_TOOLS[name][1] for name in missing)
    return (
        f"系统缺少 {' / '.join(missing)}，本次不会做{roles}，size 与 md5 的校验不受影响"
    )


def clear_check_tools_cache() -> None:
    """改了 PATH 之后要调，否则 lru_cache 里的旧结果会一直用着"""
    for _name, (probe, _role) in CHECK_TOOLS.items():
        probe.cache_clear()


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
            encoding="utf-8",
            errors="replace",
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
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        # 超时不算通过，否则截断文件会被当完好
        return ["ffmpeg 解码超时"], None
    except OSError as e:
        return [f"无法运行 ffmpeg：{e}"], None
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
            encoding="utf-8",
            errors="replace",
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
    """摘要只留前几位，md5 有雪崩效应，不符时开头必然不同，全长为噪音"""
    return digest if len(digest) <= n else digest[:n]


def check_md5(path: str, expect_md5: str, expect_size: int = 0) -> tuple[bool, str]:
    """比对大小与 md5，返回是否通过与说明

    md5 为唯一裁决者，size 在 md5 缺席时兜底
    """
    if not expect_md5 and not expect_size:
        return True, ""

    actual_size = Path(path).stat().st_size
    size_bad = bool(expect_size) and actual_size != expect_size

    if not expect_md5:
        if size_bad:
            return False, f"大小不符，声明 {expect_size} 字节，实际 {actual_size} 字节"
        return True, ""

    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    actual = h.hexdigest()
    if actual == expect_md5.lower():
        return True, ""

    # 截断为下载最常见的坏法，此时大小差异比摘要更能说明问题
    if size_bad:
        return False, (
            f"大小不符，声明 {expect_size} 字节，实际 {actual_size} 字节；"
            f"md5 不符，声明前缀 {_short_digest(expect_md5)}，"
            f"实际前缀 {_short_digest(actual)}"
        )
    return (
        False,
        f"md5 不符，声明前缀 {_short_digest(expect_md5)}，"
        f"实际前缀 {_short_digest(actual)}",
    )


def check_audio(path: str) -> tuple[bool, str]:
    """检查音频完整性，返回是否通过与说明

    三样工具各管一段，缺哪个只跳过那一段；ffmpeg 与 flac 都没有时直接放行
    """
    tools = check_tools()
    if not (tools["ffmpeg"] or tools["flac"]):
        return True, ""

    info = ffprobe_info(path) if tools["ffprobe"] else None
    declared = info["duration"] if info else None

    # 用文件名而非工具 stderr 里的路径，避免乱码
    name = Path(path).name

    errors: list[str] = []
    actual: float | None = None
    if tools["ffmpeg"]:
        errors, actual = ffmpeg_decode(path)
        if errors:
            # 尾部异常只在解码完成时放行，超时按失败处理
            note = " | ".join(errors[:3])
            if declared and actual is not None and actual >= declared - DURATION_TOL:
                return True, f"解码完整，尾部有异常数据，{name}：{note}"
            return False, f"解码出错，{name}：{note}"

    if Path(path).suffix.lower() == ".flac" and tools["flac"]:
        err = flac_test(path)
        if err:
            return False, f"flac 无损校验失败，{name}：{err}"

    if declared and actual is not None and actual < declared - DURATION_TOL:
        return False, f"疑似截断，{name}，声明 {declared:.0f} 秒，实际 {actual:.0f} 秒"

    return True, ""
