"""`--json --dlink` 在一批曲目上取下载链接

`album` 与 `playlist` 的 `--dlink` 只在 `--json` 下有意义：
单曲的 `--dlink` 打面板，而一批曲目的链接是数据。
"""

import argparse

import pytest

from function import commands

READY = {
    "id": 1,
    "url": "http://x/1.flac",
    "level": "lossless",
    "br": 999000,
    "size": 30000000,
    "md5": "aaa",
    "fee": 0,
    "expi": 1200,
}
BLOCKED = {"id": 2, "url": None, "level": None, "br": 0, "size": 0, "fee": 1}


def tracks(n, start=1):
    return [
        {
            "id": i,
            "title": f"曲目{i}",
            "artist": "A",
            "album": "B",
            "cover": "",
            "publish_time": "",
            "duration": "3:00",
        }
        for i in range(start, start + n)
    ]


def album(n=3):
    """每次给一份新的

    早先这里是模块级常量，而 _attach_downloads 是原地写 download 键，
    于是前面的测试把键留给了后面的，「没给 dlink 就不该有 download」
    那条必然红。共享的可变夹具的问题，不是生产代码的问题。
    """
    return {
        "id": 1,
        "name": "某专辑",
        "artist": "A",
        "cover": "",
        "track_count": n,
        "tracks": tracks(n),
    }


def ns(**kw):
    base = {
        "id": 1,
        "json": True,
        "download": False,
        "dlink": True,
        "lyrics": False,
        "tlyric": False,
        "quality": None,
        "output": None,
        "check": None,
        "curl": None,
        "limit": None,
        "offset": 0,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def parsed(capsys):
    """一次读完再拆成 stdout 与 stderr

    capsys.readouterr() 会清空缓冲，读第二次就只剩空的了。
    早先这里只返回 stdout，于是后面再读 err 永远拿到空串，
    「stderr 只给数量」那条测试就是这么空转的。
    """
    import json

    got = capsys.readouterr()
    return json.loads(got.out), got.out, got.err


@pytest.fixture
def two_urls(monkeypatch):
    """假装接口返回：第 1 首有链接，第 2 首拿不到，其余没返回条目"""
    calls = []

    def fake(ids, quality=None):
        calls.append(list(ids))
        out = {}
        for i in ids:
            if i == 1:
                out[i] = READY
            elif i == 2:
                out[i] = BLOCKED
        return out

    monkeypatch.setattr(commands, "fetch_player_urls", fake)
    return calls


class Test单独给dlink要报错:
    @pytest.mark.parametrize("extra", [{}, {"download": True}])
    def test_不配json就退出(self, monkeypatch, capsys, extra):
        """给了一堆参数才开始拉曲目，然后才说参数写错了"""
        monkeypatch.setattr(
            commands, "get_album_details", lambda _i: pytest.fail("不该联网")
        )
        with pytest.raises(SystemExit) as exc:
            commands.cmd_album(ns(json=False, **extra))
        assert exc.value.code == 2
        assert "--json" in capsys.readouterr().err

    def test_歌单同样(self, monkeypatch, capsys):
        monkeypatch.setattr(
            commands, "get_playlist_details", lambda _i: pytest.fail("不该联网")
        )
        with pytest.raises(SystemExit) as exc:
            commands.cmd_playlist(ns(json=False))
        assert exc.value.code == 2
        assert "--json" in capsys.readouterr().err


class Testparser:
    @pytest.mark.parametrize("name", ["song", "album", "playlist"])
    def test_三个命令都有(self, name):
        from vncmd import build_parser

        sub = next(
            a
            for a in build_parser()._actions
            if type(a).__name__ == "_SubParsersAction"
        )
        flags = [o for a in sub.choices[name]._actions for o in a.option_strings]
        assert "--dlink" in flags, f"{name} 没有 --dlink"
        assert "-u" in flags, f"{name} 的 --dlink 没有短选项"

    @pytest.mark.parametrize("name", ["album", "playlist"])
    def test_help写明要配合json(self, name, capsys):
        """从 song 过来的用户会在 album 上撞报错，help 要先说清

        断言的是「需配合」而不是「--json」：后者 argparse 的用法行里本来就有，
        断言它在就恒真了 —— 与 test_search_limit 里那条注释同一个坑。
        """
        from vncmd import build_parser

        sub = next(
            a
            for a in build_parser()._actions
            if type(a).__name__ == "_SubParsersAction"
        )
        with pytest.raises(SystemExit):
            sub.choices[name].parse_args(["--help"])
        assert "需配合 --json" in capsys.readouterr().out

    def test_song的help说的是面板(self, capsys):
        """单曲的形态是面板，与批量不同，两边文案要分开"""
        from vncmd import build_parser

        with pytest.raises(SystemExit):
            build_parser().parse_args(["song", "--help"])
        assert "需配合" not in capsys.readouterr().out


class Test批量取链接:
    def test_每条都有download键(self, monkeypatch, capsys, two_urls):
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album())
        commands.cmd_album(ns())
        data, _out, _err = parsed(capsys)
        assert [t["download"]["url"] for t in data["album"]["tracks"]] == [
            READY["url"],
            "",
            "",
        ]

    def test_拿不到时字段齐全只是值为空(self, monkeypatch, capsys, two_urls):
        """键一直在，脚本能直接 .download.url 判断，不用先问键在不在"""
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album())
        commands.cmd_album(ns())
        data, _out, _err = parsed(capsys)
        entry = data["album"]["tracks"][1]["download"]
        assert entry == {
            "url": "",
            "level": None,
            "br": 0,
            "size": 0,
            "md5": "",
            "fee": 1,
            "expi": 0,
        }

    def test_按id合并而不是按顺序(self, monkeypatch, capsys):
        """响应每条带自己的 id，靠顺序对应会在有缺失时整体错位"""
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album())
        monkeypatch.setattr(
            commands,
            "fetch_player_urls",
            lambda ids, quality=None: {3: {**READY, "url": "http://x/3.flac"}},
        )
        commands.cmd_album(ns())
        data, _out, _err = parsed(capsys)
        urls = [t["download"]["url"] for t in data["album"]["tracks"]]
        assert urls == ["", "", "http://x/3.flac"]

    def test_只给七个字段(self, monkeypatch, capsys, two_urls):
        """原始响应有三十多个字段，一半是 null，批量时能撑出十几万字"""
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album())
        commands.cmd_album(ns())
        data, _out, _err = parsed(capsys)
        assert set(data["album"]["tracks"][0]["download"]) == {
            "url",
            "level",
            "br",
            "size",
            "md5",
            "fee",
            "expi",
        }

    def test_单曲与批量同形(self, monkeypatch, capsys, two_urls):
        """两个命令的 download 键名一致，脚本写一份解析能通用"""
        monkeypatch.setattr(
            commands,
            "get_song_details",
            lambda _i: {
                "id": 1,
                "title": "曲目1",
                "artist": "A",
                "album": "B",
                "album_id": 0,
                "cover": "",
                "publish_time": "",
                "duration": "3:00",
                "track_no": 1,
                "cd_no": 1,
            },
        )
        monkeypatch.setattr(
            commands, "fetch_player_url", lambda _i, quality=None: READY
        )
        commands.cmd_song(ns(id=1, dlink=True, json=True, limit=None))
        data, _out, _err = parsed(capsys)
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album())
        commands.cmd_album(ns())
        data2, _out2, _err2 = parsed(capsys)
        assert set(data["download"]) == set(data2["album"]["tracks"][0]["download"])


class Test先切再取链接:
    def test_只为切出来的那几条请求(self, monkeypatch, capsys, two_urls):
        """反过来会为没要的那几百首发一次，stderr 还报全量的比例"""
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album(300))
        commands.cmd_album(ns(limit=2, offset=100))
        data, _out, _err = parsed(capsys)
        assert two_urls == [[101, 102]]
        assert [t["id"] for t in data["album"]["tracks"]] == [101, 102]

    def test_没给切片就全取(self, monkeypatch, capsys, two_urls):
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album(3))
        commands.cmd_album(ns())
        parsed(capsys)
        assert two_urls == [[1, 2, 3]]


class Test拿不到的报法:
    def test_stderr只给数量(self, monkeypatch, capsys, two_urls):
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album(3))
        commands.cmd_album(ns())
        _data, _out, err = parsed(capsys)
        assert "2 首拿不到链接" in err

    def test_不按fee分类(self, monkeypatch, capsys, two_urls):
        """FEE_NEED 只映射 1 与 4，而实测 fee=8 出现在三分之一的曲目上

        没有依据的分类比不给更糟：错的解释会被当成结论。
        """
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album(3))
        commands.cmd_album(ns())
        _d, _o, err = parsed(capsys)
        for word in ("会员", "购买", "权限"):
            assert word not in err, f"不该出现的分类措辞：{word}"

    def test_全部拿得到就不出声(self, monkeypatch, capsys):
        monkeypatch.setattr(
            commands,
            "fetch_player_urls",
            lambda ids, quality=None: dict.fromkeys(ids, READY),
        )
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album(3))
        commands.cmd_album(ns())
        _d, _o, err = parsed(capsys)
        assert "拿不到" not in err

    def test_数量只算切出来的那几条(self, monkeypatch, capsys):
        """全量里 1 首拿不到，用户只问 5 首时报 1/5 而不是 1/529"""
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album(300))
        monkeypatch.setattr(
            commands,
            "fetch_player_urls",
            lambda ids, quality=None: {ids[2]: BLOCKED, ids[0]: READY},
        )
        commands.cmd_album(ns(limit=5))
        _d, _o, err = parsed(capsys)
        assert "4 首拿不到链接" in err


class Test不带dlink时不查:
    def test_不该白花请求(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise AssertionError("没给 --dlink 却去查了 player/url")

        monkeypatch.setattr(commands, "fetch_player_urls", boom)
        monkeypatch.setattr(commands, "get_album_details", lambda _i: album())
        commands.cmd_album(ns(dlink=False))
        data, _out, _err = parsed(capsys)
        assert all("download" not in t for t in data["album"]["tracks"])
