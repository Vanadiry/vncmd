"""命令行用法错误的中文文案

argparse 自己的消息是英文的，而且几类错误长相差异很大：缺参数报
「the following arguments are required: id」，写错命令报「invalid choice」，
自定义 type 的报错又被包成「argument X: ...」。

这里统一成中文，并指向这一层该看哪份帮助。测试盯的是这句形状，
不是每个字 —— 但「缺少参数」「不认识的参数」「没有 X 这个命令」
这三个开头要稳定，用户靠它分辨自己错在哪一类。
"""

import argparse

import pytest

from vncmd import commands
from vncmd.cli import build_parser


def _报错(argv):
    """跑一次解析，返回捕获到的 stderr 与退出码"""
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args(argv)
    return e.value.code


class Test缺参数:
    @pytest.mark.parametrize(
        ("argv", "缺的", "帮助"),
        [
            (["song"], "id", "vncmd song -h"),
            (["search"], "query", "vncmd search -h"),
            (["album"], "id", "vncmd album -h"),
            (["playlist"], "id", "vncmd playlist -h"),
            (["tracker"], "name", "vncmd tracker -h"),
            (["tool", "check"], "path", "vncmd tool check -h"),
        ],
    )
    def test统一成缺少参数并指到帮助(self, argv, 缺的, 帮助, capsys):
        assert _报错(argv) == 2
        出错 = capsys.readouterr().err
        assert "缺少参数" in 出错, 出错
        assert 缺的 in 出错, 出错
        assert 帮助 in 出错, 出错

    def test_cookie用同一句形状(self, capsys):
        """cookie 的 value 与 --check 都是可选的，两个都没给才报错

        这一条不走 argparse，是 cmd_cookie 自己判的 —— 但话要说得一样，
        用户不用记两种说法
        """
        with pytest.raises(SystemExit) as e:
            commands.cmd_cookie(argparse.Namespace(check=False, value=None))
        assert e.value.code == 2
        出错 = capsys.readouterr().err
        assert "缺少参数" in 出错, 出错
        assert "Cookie" in 出错, 出错
        assert "vncmd cookie -h" in 出错, 出错


class Test写错命令:
    def test不认识的命令列出可用的(self, capsys):
        """cache 已经挪进 tool，直接敲会撞这里"""
        assert _报错(["cache"]) == 2
        出错 = capsys.readouterr().err
        assert "没有 cache" in 出错, 出错
        assert "可用命令" in 出错, 出错
        assert "tool" in 出错, 出错

    def test_tool下的子命令也同一套(self, capsys):
        assert _报错(["tool", "xyz"]) == 2
        出错 = capsys.readouterr().err
        assert "没有 xyz" in 出错, 出错
        assert "check" in 出错 and "cache" in 出错, 出错


class Test其他用法错误:
    def test不认识的参数(self, capsys):
        """--check 已经从下载命令上去掉了"""
        assert _报错(["song", "1", "--check"]) == 2
        出错 = capsys.readouterr().err
        assert "不认识的参数" in 出错, 出错
        assert "--check" in 出错, 出错

    def test整数位置参数写错(self, capsys):
        assert _报错(["song", "abc"]) == 2
        出错 = capsys.readouterr().err
        assert "要一个整数" in 出错, 出错
        assert "abc" in 出错, 出错

    def test取值选项没给值(self, capsys):
        assert _报错(["--config"]) == 2
        出错 = capsys.readouterr().err
        assert "需要一个值" in 出错, 出错

    def test互斥的两个同给(self, capsys):
        assert _报错(["song", "1", "--dlink", "-d"]) == 2
        出错 = capsys.readouterr().err
        assert "不能与" in 出错, 出错
        assert "同时给" in 出错, 出错

    @pytest.mark.parametrize(
        "argv",
        [["song"], ["cache"], ["song", "1", "--check"], ["song", "abc"]],
    )
    def test退出码都是二(self, argv):
        """用法错误统一退 2，脚本分「用法错」与「跑失败」只需记两个值"""
        assert _报错(argv) == 2
