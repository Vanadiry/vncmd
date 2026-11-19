"""Tracker 数据版本检查器

只负责把版本和权限请求交给规则表，并返回 Decision。
"""

from dataclasses import dataclass

from vncmd.core.data_version_rules import (
    CURRENT_TRACKER_VERSION,
    EMBED_ID_RULES,
    FUTURE_EMBED_RULE,
    FUTURE_TRACKER_RULE,
    INVALID_EMBED_RULE,
    INVALID_TRACKER_RULE,
    TRACKER_RULES,
    Rule,
    RuleMode,
)


@dataclass(frozen=True)
class Decision:
    """一次版本检查的结果"""

    allowed: bool
    message: str | None = None


def _invalid_version(version) -> bool:
    return not isinstance(version, int) or isinstance(version, bool) or version < 0


def _decide(rule: Rule, permission: str, version, name: str = "") -> Decision:
    if rule.mode == RuleMode.ALLOW:
        allowed = permission in rule.permissions
    else:
        allowed = permission not in rule.permissions

    message = None
    if rule.message:
        message = rule.message.format(
            version=version,
            current=CURRENT_TRACKER_VERSION,
            name=name,
        )
    return Decision(allowed=allowed, message=message)


def _rules_for(permission: str):
    if permission.startswith("tracker."):
        return TRACKER_RULES, FUTURE_TRACKER_RULE, INVALID_TRACKER_RULE
    if permission.startswith("embed_id."):
        return EMBED_ID_RULES, FUTURE_EMBED_RULE, INVALID_EMBED_RULE
    raise ValueError(f"未知权限命名空间：{permission}")


def check(version, permission: str, name: str = "") -> Decision:
    """检查数据版本是否允许请求的权限"""
    tracker_rules, future_rule, invalid_rule = _rules_for(permission)

    if _invalid_version(version):
        return _decide(invalid_rule, permission, version, name)

    if version > CURRENT_TRACKER_VERSION:
        return _decide(future_rule, permission, version, name)

    rule = tracker_rules.get(version, invalid_rule)
    return _decide(rule, permission, version, name)
