"""报错前缀不叠加"""

import argparse

import pytest

from vncmd import commands
from vncmd.net import api


class Test搜索失败:
    def test_api层不自带前缀(self, monkeypatch):
        """api 只原样抛出接口返回，加前缀的话命令层再包一层会成为叠词"""

        class FakeResp:
            def json(self):
                return {"code": 400}

        class FakeSession:
            def get(self, *a, **k):
                return FakeResp()

        monkeypatch.setattr(api, "_get_session", lambda: FakeSession())
        with pytest.raises(ValueError) as exc:
            api.search("x", limit=10, offset=0)
        msg = str(exc.value)
        assert msg.startswith("{"), f"api 层带了前缀：{msg}"
        assert "搜索失败" not in msg

    def test命令层拼起来只有一遍(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise ValueError("{'code': 400}")

        monkeypatch.setattr(commands, "search", boom)
        with pytest.raises(SystemExit):
            commands.cmd_search(
                argparse.Namespace(query="x", count=10, offset=0, json=True)
            )
        err = capsys.readouterr().err
        assert err.count("搜索失败") == 1, f"叠词了：{err}"
        assert "{'code': 400}" in err, "接口返回的原文要留着，那是唯一有信息量的部分"

    def test_json模式失败时stdout仍为空(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise ValueError("{'code': 400}")

        monkeypatch.setattr(commands, "search", boom)
        with pytest.raises(SystemExit):
            commands.cmd_search(
                argparse.Namespace(query="x", count=10, offset=0, json=True)
            )
        out, _err = capsys.readouterr()
        assert out == "", "失败时 stdout 必须是空的，不能是半截 JSON"


class Test仍然能报错:
    """前缀只影响措辞，报错与退出照旧"""

    @pytest.mark.parametrize("cmd", ["album", "playlist", "song"])
    def test取不到要报错并退出(self, cmd, monkeypatch, capsys):
        def boom(*a, **k):
            raise ValueError("XXX 未找到")

        name = {
            "album": "get_album_details",
            "playlist": "get_playlist_details",
            "song": "get_song_details",
        }[cmd]
        monkeypatch.setattr(commands, name, boom)
        ns = argparse.Namespace(
            id=1,
            json=False,
            download=False,
            dlink=False,
            lyric=False,
            translate=False,
            limit=None,
            quality=None,
            output=None,
            query="x",
            offset=0,
        )
        with pytest.raises(SystemExit) as exc:
            getattr(commands, f"cmd_{cmd}")(ns)
        assert exc.value.code != 0
        err = capsys.readouterr().err
        assert "XXX 未找到" in err
        assert err.count("失败") <= 1, f"叠词了：{err}"
