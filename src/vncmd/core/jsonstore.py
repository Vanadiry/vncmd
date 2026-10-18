"""JSON 读写的容错与原子替换

断电、磁盘满、kill -9、手工编辑出错都会在半截文件上停手。
裸 json.loads 读到就抛，往后每次运行都崩，且永远不会自愈；
write_text 直写最终路径时崩溃同理，只是把好文件换成了坏文件。
"""

import json
import os
from contextlib import suppress
from pathlib import Path

from vncmd.core.output import warning


def read_json_safe(path: Path, default=None, *, what: str = ""):
    """读 JSON，坏文件按 default 处理并出声

    what 是给人看的对象名，留空则用文件名。
    损坏多半来自外部，写用户数据的那些地方还要再决定是退回备份还是清空。
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        warning(f"{what or path.name} 已损坏，未能读取：{e}")
        return default


def write_json_atomic(path: Path, data: dict, *, indent: int | None = 2) -> None:
    """先写同目录的 .tmp 再 os.replace

    os.replace 在同一文件系统内是原子的，替换失败时旧文件仍是完整的。
    .tmp 与目标同目录才能保证这一点，写到系统临时目录会跨文件系统而失效。
    """
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
