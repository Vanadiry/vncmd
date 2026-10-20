"""代码风格硬约束"""

import ast
import pathlib

SRC = pathlib.Path("src")


def _取名(节点):
    """各类节点上的标识符叫什么，arg 用 .arg 而别处用 .name"""
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
    """扫出一段源码里的非 ASCII 标识符，中文注释与用户文案不受这条约束"""
    坏的 = []
    for 节点 in ast.walk(ast.parse(源码)):
        名 = _取名(节点)
        if 名 and not 名.isascii() and not 名.startswith("__"):
            坏的.append(f"{名}（第 {节点.lineno} 行）")
    return 坏的


class Test标识符:
    def test_src下没有中文标识符(self):
        """中文变量名、函数名、类名、参数名都不许有，ruff 也不查这个"""
        坏的 = []
        for f in sorted(SRC.rglob("*.py")):
            坏的 += [f"{f}:{项}" for 项 in _扫(f.read_text(encoding="utf-8"))]
        assert not 坏的, "生产代码里的标识符要用英文：\n" + "\n".join(坏的)

    def test_检查本身抓得住(self):
        """检查不能恒真，用一段已知有中文标识符的代码试，查不出问题的检查更糟"""
        # 两处：赋值处算定义，return 处只是读
        源码 = "def 下载(song_id):\n    路径 = song_id\n    return 路径\n"
        找到 = _扫(源码)
        assert len(找到) == 2, f"这段里有两个中文标识符，只找到 {找到}"

    def test_英文代码扫不出东西(self):
        """反过来也要验，把正常代码报出来会让人养成忽略它的习惯"""
        assert _扫("def fetch(song_id):\n    path = song_id\n    return path\n") == []
