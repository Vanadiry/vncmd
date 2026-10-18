"""配置键表 —— 每个键能填什么

与 `defaults.py` 是刻意重复的两份，不是冗余：
`defaults.py` 给**人**读，注释是它的主要内容，缺配置时整体写出给用户看；
这张表给**机器**读，装着取值范围与默认值，注释反而是负担。
不由表生成 toml —— 两份绑死之后，改一句注释就得改代码。

现在只搬了 6 个枚举型键，缺键仍然报错。
缺键回落默认值是 TODO2 第 4 步的事，到那时才轮得到 `default` 派上用场。
"""

from dataclasses import dataclass
from typing import Any

# 音质名到码率的映射。最大值那档用 int 上限占位 ——
# 服务端不认这个边界，发过去它自己降，所以那一档的真实规格逐曲不同
QUALITY_MAP = {
    "128": 128000,
    "192": 192000,
    "320": 320000,
    "max": 2147483647,
}

# 下载内容。三个字母任意组合，"alc" 是全要，"cl" 只要歌词和封面。
# 用字母而不是数字：数字串读起来就是个带前导零的数，
# 有人会当成整数写上引号就忘了，而 alc 一眼知道不是数字。
# 三个字母没有天然顺序，所以读的时候按包含判断，顺序无所谓
CONTENT_LETTERS = "alc"


@dataclass(frozen=True)
class Setting:
    """一个配置项。path 是点号路径

    kind 决定怎么校验：
    `enum` 查 values、`content` 走字母组合那套规则、
    `int` 查 minimum 与 maximum、`bool` 与 `str` 只查类型。

    default 是键缺失时的取值。这一栏现在还没人读 ——
    缺键回落默认值是第 4 步的事，先摆在这儿让表的形状一次定稳。

    bad 是取值不对时的措辞，miss 是缺键时的措辞。
    两者每项都不一样，不是一句模板套出来的：
    有几项带实际值、有一项写「只能是」、content 缺键要多提醒一句带引号，
    差别都是现有测试钉着的，改文案就是改行为。
    两栏都是第 6 步的东西，这轮先摆着让形状定稳
    """

    path: str
    kind: str = "str"
    values: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    default: Any = None
    bad: str = ""
    miss: str = "缺失或为空"


def _enum(
    path: str,
    values: tuple[str, ...],
    default: str,
    bad: str,
    miss: str = "缺失或为空",
) -> Setting:
    return Setting(path, "enum", values, default=default, bad=bad, miss=miss)


def _content(path: str, default: str) -> Setting:
    """content 不填 values

    它的合法值是任意字母组合，不是一组枚举值 ——
    塞进 values 只会让人以为「alc」与「ca」是两个不同的枚举项。
    合法字母留在 CONTENT_LETTERS，那是 content 专有的规则

    缺键那句要多提醒「必须是带引号的字符串」：content = 12 会被 tomllib
    读成整数，而不带引号正是这一项最常见的错
    """
    return Setting(
        path,
        "content",
        default=default,
        miss="缺失或为空，且必须是带引号的字符串",
    )


SCHEMA = (
    # 艺术家在文件名里的位置。以前这个键叫 filename_format，
    # 但它管不到分隔符、大小写、扩展名，三个值全由这一个维度决定，
    # 名字比内容宽
    _enum(
        "download.filename_artist",
        ("front", "back", "drop"),
        "back",
        "必须为 front、back、drop",
    ),
    _content("download.content", "alc"),
    # 音质名到码率的映射，合法名就是它的键
    _enum(
        "download.audio.quality",
        tuple(QUALITY_MAP),
        "max",
        # 带实际值：写 quality = 320 的人看到的是「必须为 128、192、320」，
        # 只差一对引号，报错里不写实际值就让人以为键名也错了
        "必须为以下之一：{allowed}，实际是 {value!r}",
    ),
    # 译文歌词的处理方式。前两档两边相同、第三档含义不同 ——
    # embed 是不要译文，save 多一档 split 分两个文件。
    # 各写各的，共用一个元组就把这个差别盖住了，这正是要建表的原因
    _enum(
        "download.lyric.embed_mode",
        ("line", "block", "drop"),
        "drop",
        # 这两个键带实际值：写 2 的人看到的是「必须为 line、block、drop」，
        # 而 2 是上一版方案的旧值，报错里不写实际值就看不出自己没跟着改
        "必须为 line、block、drop，实际是 {value!r}",
        # 缺键这句不带「或为空」：这两个键的合法值里没有空串，
        # 空不空都错，写「或为空」会让人以为是空值的问题
        "缺失",
    ),
    _enum(
        "download.lyric.save_mode",
        ("line", "block", "split", "drop"),
        "line",
        "必须为 line、block、split、drop，实际是 {value!r}",
        "缺失",
    ),
    _enum(
        "download.downloader",
        ("builtin", "curl"),
        "builtin",
        '只能是 "builtin" 或 "curl"',
    ),
)

_BY_PATH = {s.path: s for s in SCHEMA}

# 从表里派生，不另写一份 —— 另写一份就成了表与它各说各话的第二个来源。
# 这两个名字仍被 cli、tracker 与测试 import，等各调用点跟着搬进 schema
# 之后再删掉
FILENAME_ARTIST = _BY_PATH["download.filename_artist"].values
LYRIC_MODES = {
    "embed_mode": _BY_PATH["download.lyric.embed_mode"].values,
    "save_mode": _BY_PATH["download.lyric.save_mode"].values,
}


def get(path: str) -> Setting | None:
    """查一项。查不到返回 None，那是还没进表的键"""
    return _BY_PATH.get(path)


def check_content(value: Any, letters: str) -> str | None:
    """content 的规则不是取值集合，返回错误说明或 None

    几个部分分开说，因为错的写法不一样：
    不是字符串的是漏了引号、其余的都是没填、多余的是打错字母、
    重复的是不知道每字母最多一次

    字符串那道检查不能省：content = 12 会被 tomllib 读成整数，
    下面 set() 它会抛 TypeError，用户看到的是一整段调用栈而不是配置写错了
    """
    if not isinstance(value, str) or not value:
        return "缺失或为空，且必须是带引号的字符串"
    多余 = sorted(set(value) - set(letters))
    if 多余:
        return f"只能包含 {'、'.join(letters)}，多余的字符：{'、'.join(多余)}"
    重复 = sorted({c for c in value if value.count(c) > 1})
    if 重复:
        return f"里 {'、'.join(重复)} 重复了，每个字母最多一次"
    return None


def check_enum(setting: Setting, value: Any) -> str | None:
    """枚举校验，返回值不对时的说明或 None

    措辞从 `bad` 里来，`{allowed}` 换成值域、`{value}` 换成用户实际填的。
    带不带实际值每项不一样，所以它进得了模板而不是一句模板套所有
    """
    if value in setting.values:
        return None
    # 两个占位符各自可选：quality 的值域是四个且带逗号分隔，
    # 写死一种拼法就等于把那一项的措辞硬编进这里。
    # 一次 format 而不是逐个 replace —— replace 会先把 {value!r} 替成 {value}，
    # 后面那道再替一次，结果占位符原样留在消息里
    return setting.bad.format(allowed=", ".join(setting.values), value=value)


def validate_entry(setting: Setting, value: Any) -> str | None:
    """按 kind 分派，返回这一项的错误说明或 None

    消息里只有值本身的部分，段名与键名由 validate 拼 ——
    那边才知道这一项在哪个段里
    """
    if setting.kind == "enum":
        return check_enum(setting, value)
    if setting.kind == "content":
        return check_content(value, CONTENT_LETTERS)
    return None


def _locate(cfg: dict, path: str) -> tuple[list[str], str, Any]:
    """按点号路径在配置里取值

    返回 (段名列表, 键名, 值)。段名多于一层时就是 download.audio 这种，
    `download.filename_artist` 那种两段的则是 download 本身作为段
    """
    段 = path.split(".")
    容器 = cfg
    for 一段 in 段[:-1]:
        if not isinstance(容器, dict):
            return [], path, None
        容器 = 容器.get(一段, {})
    if not isinstance(容器, dict):
        return [], path, None
    return 段[:-1], 段[-1], 容器.get(段[-1], None)


def validate(cfg: dict) -> list[str]:
    """校验表里已进表的那几项，返回错误说明的列表

    只管表里有的键。类型、范围、缺键回落、未知键都在后面几步，
    `validate_config` 那部分手写代码还留着
    """
    错误 = []
    for setting in SCHEMA:
        段, 键, 值 = _locate(cfg, setting.path)
        if not 段:
            # 上层不是表，那一段的检查由 validate_config 报，
            # 这里再报一遍就是重复了
            continue

        段名 = "[" + ".".join(段) + "]" if len(段) > 1 else f"[{段[0]}]"
        if 值 is None:
            # 缺键这轮仍然要报错，等第 4 步才改成回落默认值
            错误.append(f"{段名} {键} {setting.miss}")
            continue

        说明 = validate_entry(setting, 值)
        if 说明:
            错误.append(f"{段名} {键} {说明}")
    return 错误
