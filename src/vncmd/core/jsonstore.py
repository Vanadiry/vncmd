"""JSON 读写的容错与原子替换"""

import json
import os
from contextlib import suppress
from pathlib import Path

from vncmd.core.output import warning


def read_json_safe(path: Path, default=None, *, what: str = ""):
    """读 JSON，坏文件按 default 处理并提示"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        warning(f"{what or path.name} 已损坏，未能读取：{e}")
        return default


def write_json_atomic(path: Path, data: dict, *, indent: int | None = 2) -> None:
    """先写同目录 .tmp 再 os.replace，保证替换原子性"""
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8"
        )
        os.replace(tmp, path)
    except OSError:
        with suppress(OSError):
            tmp.unlink()
        raise
