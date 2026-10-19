"""`--json` 的结构化输出

四条命令各加一个分支，序列化手上的归一化 dict 后退出。
它服务的是不写 Python 的那批人 —— 会写的人今天就能 `import vncmd.net.api`，
而脚本要的是能直接喂给 `jq` 与 `read` 的东西。
"""

import argparse
import json

import pytest

from vncmd import commands
from vncmd.cli import build_parser

SONG = {
    "id": 2742965504,
    # 歌名里带方括号是常事，rich 会当样式标记解析，裸 print 才不遭殃
    "title": "PPPP [Live]",
    "artist": "TAK, 初音ミク",
    "album": "PPPP",
    "cover": "https://p1.music.126.net/x.jpg",
    "publish_time": "2025-09-17 00:00:00",
    "duration": "2:34",
}

TRACKS = [
    {
        "id": 26096281,
        "title": "鏡音レンの暴走",
        "artist": "cosMo@暴走P",
        "album": "鏡音レンの暴走",
        "duration": "4:50",
    },
]

ALBUM = {
    "id": 123388631,
    "name": "叶惠美",
    "artist": "周杰伦",
    "track_count": 12,
    "tracks": TRACKS,
}

PLAYLIST = {
    "id": 17647459371,
    "name": "歌单",
    "creator": "谁",
    "track_count": 1,
    "tracks": TRACKS,
}


def ns(**kw):
    """补齐 cmd_* 会读到的全部参数，缺的都给无害的默认值"""
    base = {
        "id": 1,
        "json": False,
        "download": False,
        "dlink": False,
        "lyric": False,
        "translate": False,
        "check": None,
        "limit": None,
        "offset": 0,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def parsed(capsys):
    """读回 stdout 并解析，顺带确认它是合法 JSON"""
    out, err = capsys.readouterr()
    return json.loads(out), out, err


class Test四条命令:
    def test_song(self, monkeypatch, capsys):
        monkeypatch.setattr(commands, "get_song_details", lambda _i: SONG)
        commands.cmd_song(ns(json=True))
        data, _out, _err = parsed(capsys)
        assert list(data) == ["song"]
        assert data["song"] == SONG

    def test_album(self, monkeypatch, capsys):
        monkeypatch.setattr(commands, "get_album_details", lambda _i: ALBUM)
        commands.cmd_album(ns(json=True))
        data, _out, _err = parsed(capsys)
        assert list(data) == ["album"]
        assert data["album"] == ALBUM

    def test_playlist(self, monkeypatch, capsys):
        monkeypatch.setattr(commands, "get_playlist_details", lambda _i: PLAYLIST)
        commands.cmd_playlist(ns(json=True))
        data, _out, _err = parsed(capsys)
        assert list(data) == ["playlist"]
        assert data["playlist"] == PLAYLIST

    def test_search(self, monkeypatch, capsys):
        monkeypatch.setattr(
            commands,
            "search",
            lambda q, limit=10, offset=0: {"total": 1, "songs": TRACKS},
        )
        commands.cmd_search(ns(query="x", limit=10, offset=0, json=True))
        data, _out, _err = parsed(capsys)
        assert list(data) == ["search"]
        assert data["search"] == {"total": 1, "songs": TRACKS}


class TestJSON模式不画表格:
    def test_song没有面板(self, monkeypatch, capsys):
        monkeypatch.setattr(commands, "get_song_details", lambda _i: SONG)
        commands.cmd_song(ns(json=True))
        out = capsys.readouterr().out
        assert "曲目详情" not in out
        assert "│" not in out, "表格混进 JSON 里就解析不了了"

    def test_album没有面板(self, monkeypatch, capsys):
        monkeypatch.setattr(commands, "get_album_details", lambda _i: ALBUM)
        commands.cmd_album(ns(json=True))
        assert "专辑详情" not in capsys.readouterr().out

    def test_搜索没有表格(self, monkeypatch, capsys):
        monkeypatch.setattr(
            commands,
            "search",
            lambda q, limit=10, offset=0: {"total": 1, "songs": TRACKS},
        )
        commands.cmd_search(ns(query="x", limit=10, offset=0, json=True))
        out = capsys.readouterr().out
        assert "│" not in out


class TestJSON给全量而面板截断:
    def test_album没给limit时给全量(self, monkeypatch, capsys):
        """表格给人看要截断免得刷屏，脚本要数据就得齐"""
        many = {**ALBUM, "tracks": [dict(TRACKS[0], id=i) for i in range(12)]}
        monkeypatch.setattr(commands, "get_album_details", lambda _i: many)
        commands.cmd_album(ns(json=True, limit=None, offset=0))
        data, _out, _err = parsed(capsys)
        assert len(data["album"]["tracks"]) == 12, "JSON 要给全量，不能自己截"

    def test_album显式给了limit就按给的切(self, monkeypatch, capsys):
        """显式给了 limit 与 offset 就按给的切，与面板同一套规则。

        早先这里断言 JSON 无视 limit，那是 --limit 只有一个含义时的行为。
        用户为脚本写死一个 limit 却拿不到那么多条，比截断更难排查。
        """
        many = {**ALBUM, "tracks": [dict(TRACKS[0], id=i) for i in range(12)]}
        monkeypatch.setattr(commands, "get_album_details", lambda _i: many)
        commands.cmd_album(ns(json=True, limit=3, offset=0))
        data, _out, _err = parsed(capsys)
        assert len(data["album"]["tracks"]) == 3

    def test_album_offset只给offset时切到末尾(self, monkeypatch, capsys):
        many = {**ALBUM, "tracks": [dict(TRACKS[0], id=i) for i in range(12)]}
        monkeypatch.setattr(commands, "get_album_details", lambda _i: many)
        commands.cmd_album(ns(json=True, limit=None, offset=10))
        data, _out, _err = parsed(capsys)
        assert [t["id"] for t in data["album"]["tracks"]] == [10, 11]

    def test_面板模式仍然截断(self, monkeypatch, capsys):
        """对照：不是把截断整体去掉了，只是没给 limit 时 JSON 不截"""
        many = {**ALBUM, "tracks": [dict(TRACKS[0], id=i) for i in range(12)]}
        monkeypatch.setattr(commands, "get_album_details", lambda _i: many)
        commands.cmd_album(ns(json=False, limit=2, offset=0))
        out = capsys.readouterr().out
        assert out.count("鏡音レンの暴走") <= 2


class Test输出形状:
    def test_中文不转义(self, monkeypatch, capsys):
        """ensure_ascii=False，中文要原样可读而不是 \\uXXXX"""
        monkeypatch.setattr(commands, "get_song_details", lambda _i: SONG)
        commands.cmd_song(ns(json=True))
        out = capsys.readouterr().out
        assert "初音ミク" in out
        assert "\\u" not in out

    def test_方括号不被吃(self, monkeypatch, capsys):
        """走 rich 的话 [Live] 会被当样式标记解析掉"""
        monkeypatch.setattr(commands, "get_song_details", lambda _i: SONG)
        commands.cmd_song(ns(json=True))
        data, out, _err = parsed(capsys)
        assert data["song"]["title"] == "PPPP [Live]"
        assert "[Live]" in out

    def test_有缩进能diff(self, monkeypatch, capsys):
        monkeypatch.setattr(commands, "get_song_details", lambda _i: SONG)
        commands.cmd_song(ns(json=True))
        out = capsys.readouterr().out
        assert '\n  "song": {' in out


class Test空结果:
    def test_搜不到也是合法JSON(self, monkeypatch, capsys):
        """空 stdout 加退出码 0，脚本分不清「没搜到」与「跑挂了」"""
        monkeypatch.setattr(
            commands, "search", lambda q, limit=10, offset=0: {"total": 0, "songs": []}
        )
        commands.cmd_search(ns(query="x", limit=10, offset=0, json=True))
        data, _out, err = parsed(capsys)
        assert data == {"search": {"total": 0, "songs": []}}
        assert "未找到" not in err, "空结果不该报成异常"


class Test失败:
    def test_stdout留空退出码非零(self, monkeypatch, capsys):
        def boom(_i):
            raise ValueError("接口炸了")

        monkeypatch.setattr(commands, "get_song_details", boom)
        with pytest.raises(SystemExit) as exc:
            commands.cmd_song(ns(json=True))
        out, err = capsys.readouterr()
        assert exc.value.code != 0
        assert out == "", "失败时 stdout 必须是空的，不能是半截 JSON"
        assert "获取曲目详情失败" in err


class Test权限判定不进JSON:
    def test_search不带blocked(self, monkeypatch, capsys):
        """权限跟着账号变，同一条命令对不同用户给不同结果，
        进了稳定输出就没法缓存也没法 diff"""
        monkeypatch.setattr(
            commands,
            "search",
            lambda q, limit=10, offset=0: {"total": 1, "songs": TRACKS},
        )
        monkeypatch.setattr(
            commands, "get_account_info", lambda: {"logged_in": True, "vip": True}
        )
        commands.cmd_search(ns(query="x", limit=10, offset=0, json=True))
        data, _out, _err = parsed(capsys)
        assert "blocked" not in data["search"]
        assert "blocked" not in data["search"]["songs"][0]


class Test与下载互斥:
    """--json 与 --download 互斥，但与 --dlink 可以一起给

    这条检查手写在 main 里而不是 argparse 的互斥组：需要的是
    「--download 与 --dlink 互斥、与 --json 也互斥，而 --dlink 与 --json 不互斥」。
    互斥组是等价关系，--download 只能进一个组，表达不出这种非传递的排除。
    """

    # --dlink 只有 song 有，album 与 playlist 加它会在 argparse 就报「无法识别」
    @pytest.mark.parametrize(
        ("cmd", "dl", "该提的"),
        [
            ("song", [], ["--json", "--download"]),
            # --dlink 与 -d 同给时，argparse 的互斥组会先拦住 ——
            # 那条报错说的是 dlink 与 download，不提 --json。
            # 早先它靠「用法行里恰好印了 --json」通过，是假绿
            ("song", ["--dlink"], ["--dlink", "--download"]),
            ("album", [], ["--json", "--download"]),
            ("playlist", [], ["--json", "--download"]),
        ],
    )
    def test_同给报错(self, cmd, dl, 该提的, monkeypatch, capsys):
        import sys

        import vncmd.cli as vncmd

        monkeypatch.setattr(sys, "argv", ["vncmd", cmd, "1", "--json", *dl, "-d"])
        monkeypatch.setattr(vncmd, "acquire_lock", lambda: None)
        with pytest.raises(SystemExit) as exc:
            vncmd.main()
        assert exc.value.code == 2, "与 argparse 的用法错误同码"
        out, err = capsys.readouterr()
        assert out == ""
        for 词 in 该提的:
            assert 词 in err, err

    def test_json不在任何互斥组里(self):
        """钉住上面那条理由，防止有人「顺手」把它塞进组里，
        结果 --json --dlink 又开始报错"""
        sub = next(
            a
            for a in build_parser()._actions
            if type(a).__name__ == "_SubParsersAction"
        )
        for name in ("song", "album", "playlist"):
            for group in sub.choices[name]._mutually_exclusive_groups:
                flags = [o for a in group._group_actions for o in a.option_strings]
                assert "--json" not in flags, (
                    f"{name} 的 --json 被放进了互斥组 {flags}，"
                    "会误伤 --json --dlink 这个合法组合"
                )

    def test_dlink与download仍然互斥(self):
        """既有的那条不能因为拆组而丢掉"""
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["song", "1", "--dlink", "-d"])
        assert exc.value.code != 0


class Test与dlink同给:
    def test_两个键都给(self, monkeypatch, capsys):
        """元数据与下载信息一次拿全，后面 --link 要的就是这个组合"""
        download = {
            "url": "http://x/y.flac",
            "br": 999000,
            "level": "lossless",
            "size": 100,
            "md5": "abc",
            "expi": 1200,
            "fee": 0,
            "payed": 1,
            "code": 200,
        }
        monkeypatch.setattr(commands, "get_song_details", lambda _i: SONG)
        monkeypatch.setattr(
            commands, "fetch_player_url", lambda _i, quality=None: download
        )
        commands.cmd_song(ns(json=True, dlink=True))
        data, _out, _err = parsed(capsys)
        assert list(data) == ["song", "download"]
        assert data["song"] == SONG
        assert data["download"] == download

    def test_不给dlink就不查(self, monkeypatch, capsys):
        """不该白花一次请求去取下载信息"""
        monkeypatch.setattr(commands, "get_song_details", lambda _i: SONG)

        def boom(*a, **k):
            raise AssertionError("没给 --dlink 却去查了 player/url")

        monkeypatch.setattr(commands, "fetch_player_url", boom)
        commands.cmd_song(ns(json=True, dlink=False))
        data, _out, _err = parsed(capsys)
        assert list(data) == ["song"]


class Testparser:
    def test_四条命令都有(self):
        sub = next(
            a
            for a in build_parser()._actions
            if type(a).__name__ == "_SubParsersAction"
        )
        for name in ("search", "song", "album", "playlist"):
            flags = [o for a in sub.choices[name]._actions for o in a.option_strings]
            assert "--json" in flags, f"{name} 没有 --json"

    def test_search没有互斥(self):
        """search 没有下载动作，不存在冲突，不必硬凑一个组"""
        sub = next(
            a
            for a in build_parser()._actions
            if type(a).__name__ == "_SubParsersAction"
        )
        assert sub.choices["search"]._mutually_exclusive_groups == []
