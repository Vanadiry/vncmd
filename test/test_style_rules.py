"""代码风格的几条硬约束

这些是 lint 查不出来的，ruff 默认不管标识符用什么字符。
写成测试是为了它跟着全套一起跑 —— 放进文档或注释里，
过两个月就没人记得了，而这类问题只有靠自动检查才拦得住。
"""

import ast
import pathlib

SRC = pathlib.Path("src")


def _取名(节点):
    """各类节点上的标识符叫什么，arg 是 .arg 而别的是 .name"""
    if isinstance(节点, ast.arg):
        return 节点.arg
    if isinstance(节点, ast.Attribute):
        return 节点.attr
    if isinstance(节点, ast.Name) and isinstance(节点.ctx, ast.Store):
        return 节点.id
    if isinstance(节点, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return 节点.name
    return None


def _扫(源码: str) -> list[str]:
    """扫出一段源码里的非 ASCII 标识符

    标识符一律 ASCII。中文注释与面向用户的文案不受这条约束 ——
    那是另一回事，那条规范不在这里管
    """
    坏的 = []
    for 节点 in ast.walk(ast.parse(源码)):
        名 = _取名(节点)
        if 名 and not 名.isascii() and not 名.startswith("__"):
            坏的.append(f"{名}（第 {节点.lineno} 行）")
    return 坏的


class Test标识符:
    def test_src下没有中文标识符(self):
        """中文变量名、函数名、类名、参数名都不许有

        这条以前只有我自己记得，隔了两轮又犯了 ——
        新写的代码上下文全是中文，顺手就用上了中文变量名。
        ruff 不查这个，`ruff check` 全绿也拦不住
        """
        坏的 = []
        for f in sorted(SRC.rglob("*.py")):
            坏的 += [f"{f}:{项}" for 项 in _扫(f.read_text(encoding="utf-8"))]
        assert not 坏的, "生产代码里的标识符要用英文：\n" + "\n".join(坏的)

    def test_检查本身抓得住(self):
        """这道检查自己不能是恒真的 —— 用一段已知有中文标识符的代码试

        一个查不出问题的检查比没有检查更糟：它让人以为有保障
        """
        # 两个而不是三个：return 那处的 路径 是读不是写，
        # 只有赋值那一处算标识符的定义
        源码 = "def 下载(song_id):\n    路径 = song_id\n    return 路径\n"
        找到 = _扫(源码)
        assert len(找到) == 2, f"这段里有两个中文标识符，只找到 {找到}"

    def test_英文代码扫不出东西(self):
        """反过来也验一下，别把正常的也报出来 —— 那会让人养成忽略它的习惯"""
        assert _扫("def fetch(song_id):\n    path = song_id\n    return path\n") == []
