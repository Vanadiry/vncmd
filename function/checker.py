import hashlib
import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

DURATION_TOL = 1.0

_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")

# 三样工具各管一段校验，缺哪个只跳过那一段。
# 键的顺序就是提示里的顺序，从最通用排到最专门
CHECK_TOOLS = {
    "ffprobe": "读时长与码率，用于时长交叉验证",
    "ffmpeg": "全量解码，能查出文件截断与容器损坏",
    "flac": "flac 文件的无损流 CRC 校验",
}


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


# lru_cache 是为了 tool check 一次扫几百个文件时不反复扫 PATH。
# 代价是改了 PATH 之后拿不到新值，需要 clear_check_tools_cache()
@lru_cache(maxsize=1)
def has_ffprobe() -> bool:
    return bool(shutil.which("ffprobe"))


@lru_cache(maxsize=1)
def has_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg"))


@lru_cache(maxsize=1)
def has_flac() -> bool:
    return bool(shutil.which("flac"))


def check_tools() -> dict[str, bool]:
    """三样校验工具的可用情况，启动检查与任务开始时的提示共用一份"""
    return {
        "ffprobe": has_ffprobe(),
        "ffmpeg": has_ffmpeg(),
        "flac": has_flac(),
    }


def any_check_tool() -> bool:
    """三样里有没有一样能真正做校验的。

    ffprobe 不算 —— 它只给时长，用来和 ffmpeg 的解码结果交叉比对。
    单独装 ffprobe 时 check_audio 拿不到 actual，比对那一步直接跳过，
    于是每首歌都 fork 一个 ffprobe 然后一律放行，白跑还给出假的通过。
    """
    tools = check_tools()
    return tools["ffmpeg"] or tools["flac"]


def missing_check_tools() -> list[str]:
    return [name for name in CHECK_TOOLS if not check_tools()[name]]


def describe_missing_check_tools() -> str:
    """缺哪些校验工具，以及因此会少做哪几步。三样都在时返回空串"""
    missing = missing_check_tools()
    if not missing:
        return ""
    roles = "、".join(CHECK_TOOLS[name] for name in missing)
    return (
        f"系统缺少 {' / '.join(missing)}，"
        f"本次不会做{roles}。size 与 md5 的校验不受影响。"
    )


def clear_check_tools_cache() -> None:
    """改了 PATH 之后要调，否则 lru_cache 里的旧结果会一直用着"""
    has_ffprobe.cache_clear()
    has_ffmpeg.cache_clear()
    has_flac.cache_clear()


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
        # 超时不是通过。返回空错误列表会让调用方当成「解码完整」，
        # 那样一首 30 秒都解不完的歌会被当完好文件收进库
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
    """Check audio file integrity. Returns (ok, message).

    三样工具各管一段，缺哪个只跳过那一段 —— 装了 flac 没装 ffmpeg 的机器
    仍然能验 flac 文件。整块门控放在这里以前是开在调用方的，
    结果缺 ffmpeg 时连 flac 那一步也一起不做。

    三样都没有时无事可做，直接放行：上游声明的 size 与 md5 已经对过了。
    """
    tools = check_tools()
    if not any(tools.values()):
        return True, ""

    info = ffprobe_info(path) if tools["ffprobe"] else None
    declared = info["duration"] if info else None

    # 文件名我们自己拼。工具的 stderr 里也有路径，而那段恰恰是最可能解码失败的内容 ——
    # 让它同时承担诊断信息与唯一可能乱码的字符两个角色不稳
    name = Path(path).name

    errors: list[str] = []
    actual: float | None = None
    if tools["ffmpeg"]:
        errors, actual = ffmpeg_decode(path)
        if errors:
            # 「尾部有异常数据」只在真的解完一遍的前提下才成立。
            # 超时或起不来时 actual 是 None，落到下面判失败而不是放行
            note = " | ".join(errors[:3])
            if declared and actual is not None and actual >= declared - DURATION_TOL:
                return True, f"解码完整但尾部有异常数据 {name}: {note}"
            return False, f"解码出错 {name}: {note}"

    if Path(path).suffix.lower() == ".flac" and tools["flac"]:
        err = flac_test(path)
        if err:
            return False, f"flac 无损校验失败 {name}: {err}"

    if declared and actual is not None and actual < declared - DURATION_TOL:
        return False, f"疑似截断 {name} (声明 {declared:.0f}s 实际 {actual:.0f}s)"

    return True, ""
