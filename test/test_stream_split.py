"""stdout 与 stderr 的分工"""

import argparse
from pathlib import Path

import pytest

from vncmd.core.output import (
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
    """同时收下两个流。rich 的 Console 在构造时定下 file，redirect_stdout 换不掉"""

    def read():
        captured = capsys.readouterr()
        return captured.out, captured.err

    return read


class Test状态走stderr:
    """info / warning / success / error 为诊断信息，一律不进 stdout"""

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
        """否则上面的断言只在测 redirect 有没有生效"""
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
    """明细挂在 warning 标题下面，分家就成了一段没有标题的裸数据"""

    def test_歌单里的下架曲目进stderr(self, monkeypatch, capsys):
        from vncmd import commands

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
                count=10,
                offset=0,
                dlink=False,
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
        from vncmd import commands

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
        """否则 vncmd x > out.txt 会把报错当结果留在文件里"""
        from vncmd.core import config

        with pytest.raises(SystemExit):
            config._die(["[download] dir 缺失"])
        out, err = capsys.readouterr()
        assert out == ""
        assert "配置验证失败" in err


class Test进度条绑在stderr:
    """进度条落点与 isatty 闸门都为构造参数，只能查源码
    判错流会让进度条在重定向时消失
    """

    def test_批量进度条显式绑err_console(self):
        src = Path("src/vncmd/downloader.py").read_text(encoding="utf-8")
        assert "console=err_console" in src

    def test_单文件进度条显式绑err_console(self):
        src = Path("src/vncmd/net/download.py").read_text(encoding="utf-8")
        assert src.count("console=err_console") == 2

    def test_闸门判的是stderr不是stdout(self):
        src = Path("src/vncmd/net/download.py").read_text(encoding="utf-8")
        assert "sys.stderr.isatty()" in src
        assert "sys.stdout.isatty()" not in src, (
            "闸门还判着 stdout，`> file` 时会把进度条误关掉"
        )


class Test下载降级提示:
    """降级时要说一声且说得准，判据为本地有没有 Cookie 文件，不看接口字段"""

    @pytest.fixture(autouse=True)
    def 重置开关(self, monkeypatch):
        """降级提示整个进程只报一次，每条测试都要把它放回去，否则测试之间互相污染"""
        from vncmd import downloader

        monkeypatch.setattr(downloader, "_downgrade_notified", False)

    def test_走stderr(self, capsys, monkeypatch):
        """进度条与完成摘要为同一个视觉单元，都不该进 stdout"""
        from vncmd import downloader

        monkeypatch.setattr(downloader, "get_cookie", lambda: "NMTID=xxx")
        downloader._notify_downgrade("lossless", "exhigh")
        out, err = capsys.readouterr()
        assert out == ""
        assert "无损音质" in err

    def test_有Cookie时说权限(self, capsys, monkeypatch):
        """登录了还是拿不到那一档，那属于权限问题"""
        from vncmd import downloader

        monkeypatch.setattr(downloader, "get_cookie", lambda: "NMTID=xxx")
        downloader._notify_downgrade("lossless", "exhigh")
        assert "Cookie 权限" in capsys.readouterr().err

    def test_没Cookie时说未登录(self, capsys, monkeypatch):
        """没登录时提权限没有意义，一句“Cookie 权限不支持”只会让人奇怪"""
        from vncmd import downloader

        monkeypatch.setattr(downloader, "get_cookie", lambda: "")
        downloader._notify_downgrade("lossless", "exhigh")
        出错 = capsys.readouterr().err
        assert "未登录" in 出错
        assert "Cookie 权限" not in 出错

    def test_没Cookie时仍然说清降到了哪一档(self, capsys, monkeypatch):
        """光说“未登录”不够，用户还得知道拿到了什么"""
        from vncmd import downloader

        monkeypatch.setattr(downloader, "get_cookie", lambda: "")
        downloader._notify_downgrade("lossless", "exhigh")
        assert "超高音质" in capsys.readouterr().err

    def test_没有降级时不说话(self, capsys, monkeypatch):
        from vncmd import downloader

        monkeypatch.setattr(downloader, "get_cookie", lambda: "")
        downloader._notify_downgrade("lossless", "lossless")
        out, err = capsys.readouterr()
        assert out == "" and err == ""

    def test_整个进程只报一次(self, capsys, monkeypatch):
        """一次下载里降级二十次，用户看到一条就够，那个开关不能删"""
        from vncmd import downloader

        monkeypatch.setattr(downloader, "get_cookie", lambda: "NMTID=xxx")
        downloader._notify_downgrade("lossless", "exhigh")
        capsys.readouterr()
        downloader._notify_downgrade("lossless", "exhigh")
        assert capsys.readouterr().err == ""
