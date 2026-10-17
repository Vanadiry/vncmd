"""钉住 stdout 与 stderr 的分工

stdout 只放命令的结果（表格、面板、链接、统计），stderr 放进行中的状态与异常
（info / warning / success / error、进度条、完成汇总）。这样
`vncmd search xxx > r.txt` 写进去的全是数据，`--link` 才能直接喂给下载器。

这些断言是跟着行为走的，路由改回去就会红。
"""

import argparse
from pathlib import Path

import pytest

from function.output import (
    display_album,
    display_download_detail,
    display_lyrics,
    display_search_results,
    display_song_detail,
    err_console,
    error,
    info,
    success,
    warning,
)

TRACKS = [
    {
        "id": 26096281,
        "title": "鏡音レンの暴走",
        "artist": "cosMo@暴走P, 鏡音レン",
        "album": "鏡音レンの暴走",
        "duration": "4:50",
    },
]

SONG = {
    "id": 22699098,
    "title": "晴天",
    "artist": "周杰伦",
    "album": "叶惠美",
    "album_id": 18877,
    "cover": "http://example/cover.jpg",
    "publish_time": "2003-07-31 00:00:00",
    "duration": "4:29",
}


@pytest.fixture
def two_streams(capsys):
    """同时收下两个流

    刻意用 capsys 而不是 contextlib.redirect_stdout：rich 的 Console 在
    构造时就把 file 定下来了，redirect 换 sys.stdout 它看不见。
    """

    def read():
        captured = capsys.readouterr()
        return captured.out, captured.err

    return read


class Test状态走stderr:
    """info / warning / success / error 是诊断，一律不进 stdout"""

    @pytest.mark.parametrize(
        "fn,frag",
        [(info, "ℹ"), (warning, "⚠"), (success, "✓"), (error, "✗")],
    )
    def test_四种都不碰stdout(self, fn, frag, two_streams):
        fn("一句测试话")
        out, err = two_streams()
        assert out == "", f"{fn.__name__} 往 stdout 写了东西"
        assert frag in err

    def test_多行按行拆开(self, two_streams):
        info("第一行\n第二行")
        out, err = two_streams()
        assert out == ""
        assert err.count("ℹ") == 2

    def test_err_console确实指向stderr(self):
        """否则上面那些断言只是在测 redirect 有没有生效"""
        assert err_console.stderr is True


class Test结果走stdout:
    def test_搜索表格(self, two_streams):
        display_search_results("初音", TRACKS, 1)
        out, err = two_streams()
        assert "初音" in out and "鏡音レン" in out
        assert err == "", f"表格往 stderr 漏了东西：{err!r}"

    def test_曲目详情面板(self, two_streams):
        display_song_detail(SONG)
        out, err = two_streams()
        assert "曲目详情" in out
        assert err == ""

    def test_下载链接整条落在stdout(self, two_streams):
        url = "http://example/" + "a" * 200 + ".flac"
        display_download_detail(
            123, "歌名", {"url": url, "level": "lossless", "br": 999000, "fee": 0}
        )
        out, err = two_streams()
        assert url in out, "整条链接要完整落在 stdout 上，不折行不截断"
        assert err == ""

    def test_歌词面板(self, two_streams):
        display_lyrics("[00:00.00] 作词 : 某人")
        out, err = two_streams()
        assert "歌词" in out
        assert err == ""

    def test_专辑详情(self, two_streams):
        display_album(
            {
                "id": 1,
                "name": "叶惠美",
                "artist": "周杰伦",
                "track_count": 1,
                "tracks": TRACKS,
            },
            max_tracks=1,
        )
        out, err = two_streams()
        assert "专辑详情" in out
        assert err == ""


class Test下架明细跟警告同流:
    """明细挂在 warning 标题下面，两边分家就成了一段没有标题的裸数据"""

    def test_歌单里的下架曲目进stderr(self, monkeypatch, capsys):
        from function import commands

        monkeypatch.setattr(
            commands,
            "get_playlist_details",
            lambda _id: {
                "id": 1,
                "name": "歌单",
                "creator": "谁",
                "track_count": 1,
                "tracks": TRACKS,
                "removed_tracks": [
                    {"id": 9, "title": "没了", "artist": "无人", "album": "无"}
                ],
            },
        )
        commands.cmd_playlist(
            argparse.Namespace(
                id=1,
                limit=10,
                download=False,
                json=False,
                quality=None,
                output=None,
            )
        )
        out, err = capsys.readouterr()
        assert "已下架" in err
        assert "没了" in err, "明细要跟着标题走"
        assert "歌单详情" in out, "歌单本身的表格仍然在 stdout"


class Test账号播报:
    def test_播报不上stdout(self, monkeypatch, capsys):
        from function import commands

        monkeypatch.setattr(
            commands,
            "get_account_info",
            lambda: {"logged_in": True, "vip": True, "vip_type": 11},
        )
        monkeypatch.setattr(commands, "account_stamp", lambda: (0, False))
        monkeypatch.setattr(commands, "account_needs_check", lambda: False)
        commands.announce_account()
        out, err = capsys.readouterr()
        assert out == ""
        assert "VIP" in err


class Test配置坏了:
    def test_验证失败走stderr(self, capsys):
        """否则 `vncmd x > out.txt` 会把报错当结果留在文件里"""
        from function import config

        with pytest.raises(SystemExit):
            config._die(["[download] dir 缺失"])
        out, err = capsys.readouterr()
        assert out == ""
        assert "配置验证失败" in err


class Test进度条绑在stderr:
    """这两条只能查源码：Progress 的落点与 isatty 的闸门都是构造参数，
    没有返回值可断言。它们防的是「闸门判错流」这个具体错误 ——
    stdout 被重定向时它不是 tty，进度条会被误关掉，而 stderr 是 tty 时它该出现。
    """

    def test_批量进度条显式绑err_console(self):
        src = Path("function/downloader.py").read_text(encoding="utf-8")
        assert "console=err_console" in src

    def test_单文件进度条显式绑err_console(self):
        src = Path("function/download.py").read_text(encoding="utf-8")
        assert src.count("console=err_console") == 2

    def test_闸门判的是stderr不是stdout(self):
        src = Path("function/download.py").read_text(encoding="utf-8")
        assert "sys.stderr.isatty()" in src
        assert "sys.stdout.isatty()" not in src, (
            "闸门还判着 stdout，`> file` 时会把进度条误关掉"
        )


class Test下载降级提示:
    def test_走stderr(self, capsys):
        """进度条与完成摘要是同一个视觉单元，都不该进 stdout"""
        from function import downloader

        downloader._notify_downgrade("lossless", "exhigh")
        out, err = capsys.readouterr()
        assert out == ""
        assert "无损音质" in err

    def test_没有降级时不说话(self, capsys):
        from function import downloader

        downloader._notify_downgrade("lossless", "lossless")
        out, err = capsys.readouterr()
        assert out == "" and err == ""
