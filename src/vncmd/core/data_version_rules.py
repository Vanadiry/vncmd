"""Tracker 数据版本的规则表

权限名由代码请求、由规则放行或阻断，不维护全局权限目录。
"""

from dataclasses import dataclass
from enum import StrEnum, auto

CURRENT_TRACKER_VERSION = 1


class RuleMode(StrEnum):
    """规则模式：白名单或黑名单"""

    ALLOW = auto()
    BLOCK = auto()


@dataclass(frozen=True)
class Rule:
    """一个数据版本的权限规则

    mode 为 allow 时 permissions 是白名单，为 block 时是黑名单。
    每个版本只配一句统一提示。
    """

    mode: RuleMode
    permissions: frozenset[str]
    message: str | None = None

    def __post_init__(self):
        if not isinstance(self.mode, RuleMode):
            raise ValueError(f"未知规则模式：{self.mode}")


# 旧版本规则不会自动继承新版本的阻断。
# 升级到不兼容的新版本时，直接修改对应旧版本的规则。
TRACKER_RULES = {
    # 旧数据：黑名单为空，全部操作放行，只提示迁移
    0: Rule(
        mode=RuleMode.BLOCK,
        permissions=frozenset(),
        message="Tracker 数据版本较旧，建议运行 vncmd tracker <名称> -fF 升级。",
    ),
    # 当前版本：黑名单为空，全部放行
    1: Rule(
        mode=RuleMode.BLOCK,
        permissions=frozenset(),
    ),
}

# 高于当前版本：白名单只留 -fF 作为逃生口
FUTURE_TRACKER_RULE = Rule(
    mode=RuleMode.ALLOW,
    permissions=frozenset({"tracker.fetch_force"}),
    message=(
        "Tracker 数据版本 {version} 高于当前支持的 {current}，"
        "请升级 vncmd，或执行 -fF 重建数据。"
    ),
)

# 无法识别的版本：只留 -fF
INVALID_TRACKER_RULE = Rule(
    mode=RuleMode.ALLOW,
    permissions=frozenset({"tracker.fetch_force"}),
    message="无法识别的 Tracker 数据版本，请执行 -fF 重建数据。",
)


EMBED_ID_RULES = {
    # 旧数据：白名单为空，完全阻断
    0: Rule(
        mode=RuleMode.ALLOW,
        permissions=frozenset(),
        message="Tracker 数据版本为 0，请先运行 -fF 升级后再使用 embed-id。",
    ),
    # 当前版本：白名单只有 use
    1: Rule(
        mode=RuleMode.ALLOW,
        permissions=frozenset({"embed_id.use"}),
    ),
}

# 高于当前版本：阻断
FUTURE_EMBED_RULE = Rule(
    mode=RuleMode.ALLOW,
    permissions=frozenset(),
    message=(
        "Tracker 数据版本 {version} 高于当前支持的 {current}，"
        "请升级 vncmd 后再使用 embed-id。"
    ),
)

# 无法识别的版本：阻断
INVALID_EMBED_RULE = Rule(
    mode=RuleMode.ALLOW,
    permissions=frozenset(),
    message="无法识别的 Tracker 数据版本，请先用 -fF 重建 Tracker 数据。",
)
