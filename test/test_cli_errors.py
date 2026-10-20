"""命令行用法错误的中文文案"""

import argparse

import pytest

from vncmd import commands
from vncmd.cli import build_parser


def _报错(argv):
    """跑一次解析，返回退出码"""
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

    def test_cache必须给一个开关(self, capsys):
        """必须给一个开关，不给时误操作看起来像成功
        参数检查排在碰缓存目录之前，参数错了不该先去读盘
        """
        with pytest.raises(SystemExit) as e:
            commands.cmd_cache(argparse.Namespace(stats=False, clear=False))
        assert e.value.code == 2
        出错 = capsys.readouterr().err
        assert "缺少参数" in 出错, 出错
        assert "--stats" in 出错 and "--clear" in 出错, 出错
        assert "vncmd tool cache -h" in 出错, 出错

    def test_cookie用同一句形状(self, capsys):
        """value 与 --check 都为空才报错，这一条由 cmd_cookie 自己判
        话要与 argparse 那边的缺少参数一致
        """
        with pytest.raises(SystemExit) as e:
            commands.cmd_cookie(argparse.Namespace(check=False, value=None))
        assert e.value.code == 2
        出错 = capsys.readouterr().err
        assert "缺少参数" in 出错, 出错
        assert "Cookie" in 出错, 出错
        assert "vncmd cookie -h" in 出错, 出错


class Test写错命令:
    def test只说没有这个命令(self, capsys):
        """cache 已挪进 tool，直接敲会撞这里
        不列候选命令，列出来会让这一行很长，用户下一步看 -h 即可
        """
        assert _报错(["cache"]) == 2
        出错 = capsys.readouterr().err
        assert "没有 cache" in 出错, 出错
        assert "vncmd -h" in 出错, 出错
        assert "可用命令" not in 出错, 出错

    def test_tool下的子命令也同一套(self, capsys):
        assert _报错(["tool", "xyz"]) == 2
        出错 = capsys.readouterr().err
        assert "没有 xyz" in 出错, 出错
        assert "vncmd tool -h" in 出错, 出错


class Test其他用法错误:
    def test不认识的参数(self, capsys):
        """--check 已从下载命令移除"""
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
        """用法错误统一退 2，脚本分“用法错”与“跑失败”只需记两个值"""
        assert _报错(argv) == 2
