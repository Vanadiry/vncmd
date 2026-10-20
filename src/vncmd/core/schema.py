"""配置键表，定义每个键的取值范围与默认值

与 defaults.py 的 TOML 模板分开维护，模板给人读，这张表给代码读
"""

from dataclasses import dataclass
from typing import Any

# 缓存有效期默认天数，与默认模板保持一致
DEFAULT_CACHE_TTL = 3

# 音质名到码率，max 用 int 上限让服务端自行降级
QUALITY_MAP = {
    "128": 128000,
    "192": 192000,
    "320": 320000,
    "max": 2147483647,
}

# 下载内容字母，任意组合，alc 为全要
CONTENT_LETTERS = "alc"


@dataclass(frozen=True)
class Setting:
    """一个配置项

    kind 决定校验方式，default 为缺键回落值，wrong_value 为错误措辞
    wrong_value 不能为空，留空会让该项静默放行
    """

    path: str
    kind: str = "str"
    values: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    default: Any = None
    wrong_value: str = ""


def _enum(
    path: str,
    values: tuple[str, ...],
    default: str,
    wrong_value: str,
) -> Setting:
    return Setting(path, "enum", values, default=default, wrong_value=wrong_value)


def _content(path: str, default: str) -> Setting:
    """content 使用字母组合规则，不填 values

    wrong_value 留空，措辞由 check_content 按实际值生成
    """
    return Setting(path, "content", default=default)


SCHEMA = (
    # 文件名中艺术家的位置
    _enum(
        "download.filename_artist",
        ("front", "back", "drop"),
        "back",
        "不合法，应当为 front、back、drop",
    ),
    _content("download.content", "alc"),
    # 音质名到码率的映射，合法名即它的键
    _enum(
        "download.audio.quality",
        tuple(QUALITY_MAP),
        "max",
        # 带实际值，提醒缺引号的情况
        "不合法，可选 {allowed}，实际是 {value!r}",
    ),
    # 译文歌词处理方式，embed 不要译文，save 多一档 split
    _enum(
        "download.lyric.embed_mode",
        ("line", "block", "drop"),
        "drop",
        # 带实际值，便于发现旧配置值
        "不合法，应当为 line、block、drop，实际是 {value!r}",
    ),
    _enum(
        "download.lyric.save_mode",
        ("line", "block", "split", "drop"),
        "line",
        "不合法，应当为 line、block、split、drop，实际是 {value!r}",
    ),
    _enum(
        "download.downloader",
        ("builtin", "curl"),
        "builtin",
        '不合法，应当为 "builtin" 或 "curl"',
    ),
    # 类型与范围项的措辞逐字保留，既有测试按原文断言
    # dir 空串合法，只判类型不判非空
    Setting(
        "download.dir",
        "str",
        default="",
        wrong_value="不合法，应当为字符串，实际是 {typename}",
        # 空串合法，缺键与写空串不同
    ),
    Setting(
        "download.concurrency",
        "int",
        minimum=1,
        maximum=16,
        default=4,
        # 带实际值，缺键也用这句
        wrong_value="不合法，应当为 1 至 16 的整数，实际是 {value!r}",
    ),
    Setting(
        "download.check",
        "bool",
        default=True,
        wrong_value="不合法，应当为 true 或 false",
    ),
    Setting(
        "download.curl_arg",
        "str",
        default="",
        wrong_value="不合法，应当为字符串",
        # 省略时取默认空串
    ),
    Setting(
        "download.audio.parse_credits",
        "bool",
        default=False,
        # 布尔没有空状态，缺键与类型错共用一句
        wrong_value="不合法，应当为 true 或 false",
    ),
    Setting(
        "download.lyric.auto_trim",
        "bool",
        default=False,
        # 布尔没有空状态，缺键与类型错共用一句
        wrong_value="不合法，应当为 true 或 false",
    ),
    Setting(
        "download.lyric.credit_scan_lines",
        "int",
        minimum=1,
        default=10,
        wrong_value="不合法，应当为正整数",
    ),
    # 合法值含 false，判键是否存在而非真值
    Setting(
        "download.cover.embed_compress",
        "bool",
        default=True,
        wrong_value="不合法，应当为 true 或 false，实际是 {value!r}",
    ),
    Setting(
        "download.cover.save_compress",
        "bool",
        default=False,
        wrong_value="不合法，应当为 true 或 false，实际是 {value!r}",
    ),
    # "false" 字符串为真值，必须判类型
    Setting(
        "cache.enabled",
        "bool",
        default=True,
        wrong_value="不合法，应当为 true 或 false，实际是 {value!r}",
    ),
    Setting(
        "cache.ttl",
        "int",
        minimum=0,
        default=DEFAULT_CACHE_TTL,
        wrong_value="不合法，应当为非负整数",
    ),
    Setting(
        "display.artist_color",
        "bool",
        default=True,
        wrong_value="不合法，应当为 true 或 false",
    ),
)

_BY_PATH = {s.path: s for s in SCHEMA}

# 从表里派生，避免第二个来源
FILENAME_ARTIST = _BY_PATH["download.filename_artist"].values
LYRIC_MODES = {
    "embed_mode": _BY_PATH["download.lyric.embed_mode"].values,
    "save_mode": _BY_PATH["download.lyric.save_mode"].values,
}


def get(path: str) -> Setting | None:
    """查一项。查不到返回 None，那是还没进表的键"""
    return _BY_PATH.get(path)


def section_names() -> tuple[str, ...]:
    """表里用到的段名，含子表

    从 SCHEMA 推导，避免手写遗漏
    """
    top = set()
    sub = set()
    for setting in SCHEMA:
        parts = setting.path.split(".")
        top.add(parts[0])
        for part in parts[1:-1]:
            sub.add(f"{parts[0]}.{part}")
    return tuple(sorted(top | sub))


def coerce(path: str, raw: str) -> Any:
    """把命令行字符串按配置项类型转换

    bool 只认小写 true/false，未知路径抛 ValueError
    """
    setting = get(path)
    if setting is None:
        raise ValueError(f"配置项 {path} 不存在")
    if setting.kind == "bool":
        if raw == "true":
            return True
        if raw == "false":
            return False
        raise ValueError(f"{path} 不合法，应当为 true 或 false，实际是 {raw!r}")
    if setting.kind == "int":
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"{path} 不合法，应当为整数，实际是 {raw!r}") from None
    return raw


def split_override(text: str) -> tuple[str, str]:
    """按第一个等号切 key=value，值里允许等号"""
    if "=" not in text:
        raise ValueError(f"{text!r} 不合法，应当为 key=value")
    key, value = text.split("=", 1)
    if not key:
        raise ValueError(f"{text!r} 的 key 为空")
    return key, value


def check_content(value: Any, letters: str) -> str | None:
    """校验 content 字母组合，返回错误说明或 None

    多余与重复分别报，非字符串报缺引号
    """
    if not isinstance(value, str):
        return f"不合法，应当为带引号的字符串，实际是 {type(value).__name__}"
    if not value:
        return "缺失或为空，应当为带引号的字符串"
    extra = sorted(set(value) - set(letters))
    if extra:
        return f"不合法，只能包含 {'、'.join(letters)}，多余字符：{'、'.join(extra)}"
    dup = sorted({c for c in value if value.count(c) > 1})
    if dup:
        return f"不合法，{'、'.join(dup)} 重复，每个字母最多一次"
    return None


def check_enum(setting: Setting, value: Any) -> str | None:
    """枚举校验，返回错误说明或 None"""
    if value in setting.values:
        return None
    # 一次 format，避免逐个 replace 把占位符再替换一次
    return setting.wrong_value.format(
        allowed=", ".join(setting.values),
        value=value,
        typename=type(value).__name__,
    )


def check_int(setting: Setting, value: Any) -> str | None:
    """整数校验，返回错误说明或 None

    布尔要单独排除，否则 true 会按 1 通过
    """
    if not isinstance(value, int) or isinstance(value, bool):
        return setting.wrong_value.format(
            allowed="", value=value, typename=type(value).__name__
        )
    if setting.minimum is not None and value < setting.minimum:
        return setting.wrong_value.format(
            allowed="", value=value, typename=type(value).__name__
        )
    if setting.maximum is not None and value > setting.maximum:
        return setting.wrong_value.format(
            allowed="", value=value, typename=type(value).__name__
        )
    return None


def check_bool(setting: Setting, value: Any) -> str | None:
    """布尔校验，必须用 isinstance，避免 0 == false 放行整数"""
    if not isinstance(value, bool):
        return setting.wrong_value.format(
            allowed="", value=value, typename=type(value).__name__
        )
    return None


def check_str(setting: Setting, value: Any) -> str | None:
    """字符串校验，不判非空，报类型名而非值"""
    if not isinstance(value, str):
        return setting.wrong_value.format(
            allowed="", value=value, typename=type(value).__name__
        )
    return None


def validate_entry(setting: Setting, value: Any) -> str | None:
    """按 kind 分派校验，返回错误说明或 None"""
    if setting.kind == "enum":
        return check_enum(setting, value)
    if setting.kind == "content":
        return check_content(value, CONTENT_LETTERS)
    if setting.kind == "int":
        return check_int(setting, value)
    if setting.kind == "bool":
        return check_bool(setting, value)
    if setting.kind == "str":
        return check_str(setting, value)
    return None


def _locate(cfg: dict, path: str) -> tuple[list[str], str, Any]:
    """按点号路径取值，返回段名、键名与值"""
    parts = path.split(".")
    container = cfg
    for part in parts[:-1]:
        if not isinstance(container, dict):
            return [], path, None
        container = container.get(part, {})
    if not isinstance(container, dict):
        return [], path, None
    return parts[:-1], parts[-1], container.get(parts[-1], None)


def unknown_keys(cfg: dict) -> list[str]:
    """列出配置里表里没有的段与键

    未知键一律报错，避免改名后旧键静默失效
    """
    extra = []
    for name, table in cfg.items():
        if not _has_known_keys(name):
            # 顶层未知键必须在类型判断前报出，否则拼错的标量会被跳过
            extra.append(f"[{name}]")
            continue
        if not isinstance(table, dict):
            # 已知段写成标量时由 validate_config 报
            continue
        extra += _scan_table(name, table)
    return extra


def _scan_table(prefix: str, table: dict) -> list[str]:
    """递归检查一层键，prefix 为本层段名"""
    extra = []
    for key, value in table.items():
        path = f"{prefix}.{key}"
        if path in _BY_PATH:
            # 已知叶子键，子表继续递归
            if isinstance(value, dict):
                extra += _scan_table(path, value)
            continue
        if isinstance(value, dict):
            if _has_known_keys(path):
                # 表里也有的子表，继续查多余键
                extra += _scan_table(path, value)
            else:
                # 整段未知只报段名
                extra.append(f"[{path}]")
        else:
            extra.append(f"[{path}]")
    return extra


def _has_known_keys(prefix: str) -> bool:
    """这个段下面有没有表里认得的键"""
    return any(s.path.startswith(f"{prefix}.") for s in SCHEMA)


def value_of(cfg: dict, path: str) -> Any:
    """按 path 取值，缺失时回落默认值"""
    setting = get(path)
    if setting is None:
        # 表里没有的键原样返回，由调用方处理
        return _locate(cfg, path)[2]
    _, _, value = _locate(cfg, path)
    if value is None:
        return setting.default
    return value


def validate(cfg: dict) -> list[str]:
    """校验表里全部配置项，返回错误列表

    缺键不报错，段本身非表由 validate_config 处理
    """
    errors = []
    for setting in SCHEMA:
        parts, key, value = _locate(cfg, setting.path)
        if not setting.wrong_value and setting.kind != "content":
            # wrong_value 为空会让该项静默放行，content 由 check_content 生成措辞
            errors.append(f"[{setting.path}] 配置表缺少错误提示，该项校验不会生效")
            continue
        if not parts:
            continue

        if value is None:
            continue

        message = validate_entry(setting, value)
        if message:
            name = "[" + ".".join(parts) + "]" if len(parts) > 1 else f"[{parts[0]}]"
            errors.append(f"{name} {key} {message}")
    return errors
