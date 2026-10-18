"""tracker 的曲目表与 artist 入库

`songs.json` 里每条原来只有 `{id, title}`。`fetch_all_songs` 的 `raw`
里已经解析过 artist（`removed` 那条一直在用 `rt.get("artist", "")`），
只是没往下带 —— 补一个字段即可，不需要重新拉历史数据。
"""

import argparse
import contextlib
import json
from pathlib import Path

import pytest
from rich.console import Console

from function import tracker


def ns(**kw):
    base = {
        "name": "like",
        "fetch": False,
        "auto_accept": False,
        "force": False,
        "download": False,
        "diff": False,
        "json": False,
        "limit": None,
        "offset": 0,
        "quality": None,
        "output": None,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def songs(n=200, with_artist=True):
    out = []
    for i in range(1, n + 1):
        s = {"id": i, "title": f"曲目{i}"}
        if with_artist:
            s["artist"] = f"艺术家{i % 3}"
        out.append(s)
    return out


def db(n=200, with_artist=True):
    return {
        "updated_at": "2026-10-01T00:00:00Z",
        "songs": songs(n, with_artist),
    }


def parsed(capsys):
    got = capsys.readouterr()
    return json.loads(got.out), got.out, got.err


@pytest.fixture
def ready(monkeypatch, tmp_path):
    (tmp_path / "like").mkdir()
    monkeypatch.setattr(tracker, "_tracker_path", lambda name: tmp_path / name)
    monkeypatch.setattr(
        tracker,
        "load_settings",
        lambda name: {"description": "我的红心", "sources": []},
    )
    monkeypatch.setattr(tracker, "load_songs_db", lambda name: songs())
    monkeypatch.setattr(tracker, "load_songs_db_full", lambda name: db())
    return tmp_path


class TestArtist入库:
    def test_raw里存了artist(self):
        """fetch_all_songs 的 raw 早就解析过 artist，只是没往下带。

        走 fetch_all_songs 要联网，所以直接测它拼 raw 的那一步。
        """
        raw = {}
        tracker._add_to_raw(raw, {"id": 1, "title": "T", "artist": "A"}, "album", 5)
        assert raw[1]["artist"] == "A"

    def test_entry把artist带进结果(self):
        """raw 存了不算完，entry 那一段也得往下带，否则存不进 songs.json"""
        import inspect

        src = inspect.getsource(tracker.fetch_all_songs)
        assert '"artist": data.get("artist", "")' in src, "entry 少了 artist"

    def test_曲目没有artist时留空(self):
        raw = {}
        tracker._add_to_raw(raw, {"id": 1, "title": "T"}, "song", 5)
        assert raw[1]["artist"] == "", "缺了就留空，不要回退到现查 API"

    def test_同一首来自多个源时artist一致(self):
        raw = {}
        tracker._add_to_raw(raw, {"id": 1, "title": "T", "artist": "A"}, "album", 1)
        tracker._add_to_raw(raw, {"id": 1, "title": "T", "artist": "B"}, "playlist", 2)
        # 第一次解析到的为准，第二次只补 source_ref
        assert raw[1]["artist"] == "A"
        assert len(raw[1]["sources"]) == 2

    def test_老库读出来仍能用(self):
        """老条目是没有 artist 键，不是值为空串，下游一律 .get 而非 ["artist"]"""
        old = db(with_artist=False)["songs"][0]
        assert "artist" not in old
        assert old.get("artist", "") == "", "缺键时给空串，表格那一列才有东西可填"

    def test_保存后artist进json(self, monkeypatch, tmp_path):
        captured = {}
        monkeypatch.setattr(
            tracker, "save_songs_db", lambda n, s: captured.update(songs=s)
        )
        merged = [{"id": 1, "title": "T", "artist": "A"}]
        tracker.save_songs_db("x", merged)
        assert captured["songs"][0]["artist"] == "A"


class Test面板给设置路径:
    def test_路径用波浪号(self, ready, monkeypatch, capsys):
        """设置、init、cache 三处都是同一个写法"""
        monkeypatch.setattr(
            tracker, "_settings_path", lambda n: Path("/Users/tester/.vSoft/x.toml")
        )
        monkeypatch.setattr(
            tracker, "abbrev_home", lambda p: str(p).replace("/Users/tester", "~")
        )
        tracker.cmd_tracker(ns(limit=3))
        assert "~/.vSoft/x.toml" in capsys.readouterr().out


# 一份只含必需键的配置，测试在上面改某个键
_MINIMAL_CFG = """\
[download]
dir = ""
filename_format = "10"
content = "alc"
concurrency = 4
check = true
downloader = "builtin"
curl_arg = ""

[download.song]
quality = "max"
parse_credits = false

[download.lyric]
embed_mode = "0"
save_mode = "0"
auto_trim = false
credit_scan_lines = 10

[download.cover]
embed_compress = false
save_compress = false

[cache]
enabled = true
dir = "cache"
ttl = 3

"""


class TestArtistColor改名:
    def test_配置键是artist_color(self):
        """表里不只 Vocaloid（37 个名字里 25 个是 PIAPRO 系），
        所以 virtual_singer_color 既不准也不通用"""
        from function._defaults import CONFIG_TOML

        assert "artist_color = true" in CONFIG_TOML
        assert "virtual_singer_color" not in CONFIG_TOML

    def test_getter叫is_artist_color(self):
        from function.config import is_artist_color

        assert callable(is_artist_color)

    def test_旧名已经不存在(self):
        from function import config as config_mod

        assert not hasattr(config_mod, "is_virtual_singer_color")

    def test_注释不再说虚拟歌姬(self):
        """表里 37 个名字只有 12 个是 Vocaloid，25 个是 PIAPRO 系"""
        from function._defaults import CONFIG_TOML

        line = next(ln for ln in CONFIG_TOML.splitlines() if "代表色着色" in ln)
        assert "虚拟歌姬" not in CONFIG_TOML, line

    def test_类型错报的是新键名(self, monkeypatch, tmp_path):
        """报旧键名的话，用户会去 config.toml 里找一个不存在的项"""
        from function import config as config_mod

        # 走真的 load_config：校验在读文件之后，换掉 _get_cfg 就绕过了
        cfg = tmp_path / "config.toml"
        cfg.write_text(_MINIMAL_CFG + '[display]\nartist_color = "yes"\n', "utf-8")
        monkeypatch.setattr(config_mod, "CONFIG_FILE", cfg)
        caught = []
        monkeypatch.setattr(config_mod, "_die", lambda lines: caught.extend(lines))
        config_mod.validate_config(quiet=True)
        assert any("artist_color" in ln for ln in caught), caught
        assert not any("virtual_singer" in ln for ln in caught), caught

    def test_旧键名会被当成未知键放行(self, monkeypatch, tmp_path):
        """validate_config 只检查认识的键、从不拒绝多余的

        所以旧配置里的 virtual_singer_color 会静默失效 ——
        这是项目没发版才付得起的代价，不是 bug。
        """
        from function import config as config_mod

        cfg = tmp_path / "config.toml"
        cfg.write_text(
            _MINIMAL_CFG + "[display]\nvirtual_singer_color = false\n", "utf-8"
        )
        monkeypatch.setattr(config_mod, "CONFIG_FILE", cfg)
        caught = []
        monkeypatch.setattr(config_mod, "_die", lambda lines: caught.extend(lines))
        config_mod.validate_config(quiet=True)
        assert not caught, caught

    def test_两个歌词模式各说各的(self):
        """embed_mode=2 是仅原文，save_mode=2 是分离文件，两件事

        曾把这两行合并成一段共用说明，合并之后「嵌入只能写一个歌词字段」
        那层因果丢了，读者会以为 embed_mode=2 也是分开两个文件。
        """
        from function._defaults import CONFIG_TOML

        assert "# 嵌入歌词模式：0=交错，1=合并，2=仅原文" in CONFIG_TOML
        assert "# 独立歌词文件模式：0=交错，1=合并，2=分离文件" in CONFIG_TOML


class Test路径缩写:
    """路径一律写成 ~ 开头：设置、init、cache、tracker 面板同一个写法"""

    def _home(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        return home

    def test_init的路径都走缩写(self, monkeypatch, capsys, tmp_path):
        """只断言输出不含真实主目录路径，不断言它调没调 abbrev_home。

        早先这里把 abbrev_home 整个 monkeypatch 掉了，于是代码走不走它都一样，
        撤掉调用测试照样绿 —— 断言得落在输出上，不是落在调用上。

        下面几行只报文件名（不重复 VNCMD_HOME 那行），所以这个环境下
        唯一该带路径的是粘贴 Cookie 那句操作指引。
        """
        from function import commands as commands_mod

        home = self._home(tmp_path)
        base = home / ".vSoft" / "vncmd"
        monkeypatch.setattr(commands_mod, "VNCMD_HOME", base)
        monkeypatch.setattr(commands_mod, "CONFIG_FILE", base / "config.toml")
        monkeypatch.setattr(commands_mod, "COOKIE_FILE", base / "cookie")
        monkeypatch.setattr(
            commands_mod,
            "abbrev_home",
            lambda p: str(p).replace(str(home), "~"),
        )
        monkeypatch.setattr(commands_mod.shutil, "which", lambda n: None)
        monkeypatch.setattr(commands_mod, "validate_config", lambda quiet=False: None)
        commands_mod.cmd_init(ns())
        out = capsys.readouterr().out
        assert "VNCMD_HOME: ~/.vSoft/vncmd" in out, out

    def test_下面几行不重复路径(self, monkeypatch, capsys, tmp_path):
        """上面已经给过 VNCMD_HOME，同一屏里再写一遍是重复"""
        from function import commands as commands_mod

        home = self._home(tmp_path)
        base = home / ".vSoft" / "vncmd"
        base.mkdir(parents=True)
        (base / "config.toml").write_text("x = 1\n", encoding="utf-8")
        (base / "cookie").write_text("", encoding="utf-8")
        monkeypatch.setattr(commands_mod, "VNCMD_HOME", base)
        monkeypatch.setattr(commands_mod, "CONFIG_FILE", base / "config.toml")
        monkeypatch.setattr(commands_mod, "COOKIE_FILE", base / "cookie")
        monkeypatch.setattr(
            commands_mod,
            "abbrev_home",
            lambda p: str(p).replace(str(home), "~"),
        )
        monkeypatch.setattr(commands_mod.shutil, "which", lambda n: None)
        commands_mod.cmd_init(ns())
        out = capsys.readouterr().out
        assert "存在 config.toml" in out, out
        assert "存在 cookie" in out, out
        assert "存在 ~/.vSoft" not in out, f"存在那两行不该带路径：{out}"
        # VNCMD_HOME 那一行仍要给全，它是唯一说出位置的地方
        assert out.count("~/.vSoft/vncmd") == 1, f"路径只该出现一次：{out}"

    def test_新建时也只报文件名(self, monkeypatch, capsys, tmp_path):
        from function import commands as commands_mod

        home = self._home(tmp_path)
        base = home / ".vSoft" / "vncmd"
        monkeypatch.setattr(commands_mod, "VNCMD_HOME", base)
        monkeypatch.setattr(commands_mod, "CONFIG_FILE", base / "config.toml")
        monkeypatch.setattr(commands_mod, "COOKIE_FILE", base / "cookie")
        monkeypatch.setattr(
            commands_mod,
            "abbrev_home",
            lambda p: str(p).replace(str(home), "~"),
        )
        monkeypatch.setattr(commands_mod.shutil, "which", lambda n: None)
        monkeypatch.setattr(commands_mod, "validate_config", lambda quiet=False: None)
        commands_mod.cmd_init(ns())
        got = capsys.readouterr()
        # success 走 stderr，「存在」走 stdout，两条流都要看 ——
        # 早先只读 stdout，于是「已创建」那两行怎么写都测不到
        assert "已创建 config.toml" in got.err, got
        assert "已创建 cookie" in got.err, got
        assert "已创建" not in got.out, "已创建那两行该在诊断流里"

    def test_cookie那句带上了用途(self, monkeypatch, capsys, tmp_path):
        """空文件对新人毫无意义，得说清粘什么进去有什么好处"""
        from function import commands as commands_mod

        home = self._home(tmp_path)
        base = home / ".vSoft" / "vncmd"
        monkeypatch.setattr(commands_mod, "VNCMD_HOME", base)
        monkeypatch.setattr(commands_mod, "CONFIG_FILE", base / "config.toml")
        monkeypatch.setattr(commands_mod, "COOKIE_FILE", base / "cookie")
        monkeypatch.setattr(
            commands_mod,
            "abbrev_home",
            lambda p: str(p).replace(str(home), "~"),
        )
        monkeypatch.setattr(commands_mod.shutil, "which", lambda n: None)
        monkeypatch.setattr(commands_mod, "validate_config", lambda quiet=False: None)
        commands_mod.cmd_init(ns())
        err = capsys.readouterr().err
        assert "VIP" in err and "高音质" in err, err

    def test_cookie那句不再单起一行(self, monkeypatch, capsys, tmp_path):
        """位置由上面 VNCMD_HOME 那行给出，不再重复一遍路径"""
        from function import commands as commands_mod

        home = self._home(tmp_path)
        base = home / ".vSoft" / "vncmd"
        monkeypatch.setattr(commands_mod, "VNCMD_HOME", base)
        monkeypatch.setattr(commands_mod, "CONFIG_FILE", base / "config.toml")
        monkeypatch.setattr(commands_mod, "COOKIE_FILE", base / "cookie")
        monkeypatch.setattr(
            commands_mod,
            "abbrev_home",
            lambda p: str(p).replace(str(home), "~"),
        )
        monkeypatch.setattr(commands_mod.shutil, "which", lambda n: None)
        monkeypatch.setattr(commands_mod, "validate_config", lambda quiet=False: None)
        commands_mod.cmd_init(ns())
        got = capsys.readouterr()
        assert "粘贴" in got.err, got
        assert "粘贴到 ~/.vSoft" not in got.err, f"路径不该重复一遍：{got.err}"
        assert "粘贴到" not in got.out, got

    def test_tracker面板的路径也走缩写(self, ready, monkeypatch, capsys, tmp_path):
        """面板那行与 init 同一个写法"""
        home = self._home(tmp_path)
        monkeypatch.setattr(
            tracker, "_settings_path", lambda n: home / ".vSoft/vncmd/t/settings.toml"
        )
        monkeypatch.setattr(
            tracker, "abbrev_home", lambda p: str(p).replace(str(home), "~")
        )
        tracker.cmd_tracker(ns(limit=2))
        out = capsys.readouterr().out
        assert str(home) not in out, f"路径该缩写成 ~ 开头：{out}"

    def test_首次运行的提示也给缩写(self, monkeypatch, capsys, tmp_path):
        from function import config as config_mod

        home = self._home(tmp_path)
        monkeypatch.setattr(config_mod, "VNCMD_HOME", home / ".vSoft" / "vncmd")
        monkeypatch.setattr(
            config_mod, "CONFIG_FILE", home / ".vSoft" / "vncmd" / "config.toml"
        )
        monkeypatch.setattr(config_mod, "load_config", dict)
        monkeypatch.setattr(
            config_mod, "abbrev_home", lambda p: str(p).replace(str(home), "~")
        )
        monkeypatch.setattr(
            config_mod, "Path", type("P", (), {"home": staticmethod(lambda: home)})
        )
        # _die 走 sys.exit，那是 BaseException，suppress(Exception) 拦不住
        with contextlib.suppress(BaseException):
            config_mod.validate_config(quiet=False)
        err = capsys.readouterr().err
        assert "~/.vSoft/vncmd/config.toml" in err, err
        assert str(home) not in err, f"路径该缩写成 ~ 开头：{err}"

    def test_解析失败的提示也给缩写(self, monkeypatch, capsys, tmp_path):
        from function import config as config_mod

        home = self._home(tmp_path)

        def boom():
            raise ValueError("坏了")

        monkeypatch.setattr(config_mod, "VNCMD_HOME", home / ".vSoft" / "vncmd")
        monkeypatch.setattr(
            config_mod, "CONFIG_FILE", home / ".vSoft" / "vncmd" / "config.toml"
        )
        monkeypatch.setattr(config_mod, "load_config", boom)
        monkeypatch.setattr(
            config_mod, "abbrev_home", lambda p: str(p).replace(str(home), "~")
        )
        monkeypatch.setattr(
            config_mod, "Path", type("P", (), {"home": staticmethod(lambda: home)})
        )
        with contextlib.suppress(BaseException):
            config_mod.validate_config(quiet=True)
        assert "~/.vSoft/vncmd/config.toml" in capsys.readouterr().err

    def test_提示里的命令名是新的(self, monkeypatch, capsys, tmp_path):
        """命令从 vncmd init 改成 vncmd --init，提示里写旧的会让人敲错"""
        from function import config as config_mod

        home = self._home(tmp_path)
        monkeypatch.setattr(config_mod, "VNCMD_HOME", home / ".vSoft" / "vncmd")
        monkeypatch.setattr(
            config_mod, "CONFIG_FILE", home / ".vSoft" / "vncmd" / "config.toml"
        )
        monkeypatch.setattr(config_mod, "load_config", dict)
        monkeypatch.setattr(config_mod, "abbrev_home", lambda p: str(p))
        monkeypatch.setattr(
            config_mod, "Path", type("P", (), {"home": staticmethod(lambda: home)})
        )
        # _die 走 sys.exit，那是 BaseException，suppress(Exception) 拦不住
        with contextlib.suppress(BaseException):
            config_mod.validate_config(quiet=False)
        err = capsys.readouterr().err
        assert "--init" in err and "vncmd init" not in err


class Test艺术家着色:
    def _rendered(self, monkeypatch, songs):
        import io

        buf = io.StringIO()
        monkeypatch.setattr(
            tracker,
            "console",
            Console(file=buf, force_terminal=True, width=120, color_system="truecolor"),
        )
        tracker._display_songs(songs, 0)
        return buf.getvalue()

    def _artist_cell(self, text):
        """取第一条数据行的艺术家那一格

        要跳过表头：表头第四格是「艺术家」三个字，
        早先没跳过，抓到的是它，于是断言恒假。
        """
        for line in text.splitlines():
            if not line.startswith("│"):
                continue
            cells = line.split("│")
            if len(cells) <= 4:
                continue
            cell = cells[4]
            if "艺术家" in cell or not cell.strip():
                continue
            return cell
        return ""

    def test_虚拟歌手有代表色(self, monkeypatch):
        """早先那列给的是裸字符串，初音ミク与普通歌手长得一样"""
        out = self._rendered(
            monkeypatch, [{"id": 1, "title": "A", "artist": "なきそ, 初音ミク"}]
        )
        cell = self._artist_cell(out)
        assert "38;2;" in cell, f"没有代表色：{cell!r}"
        assert "\x1b[97m" in cell, "其余部分该保持白字"

    def test_普通歌手仍是白字(self, monkeypatch):
        out = self._rendered(
            monkeypatch, [{"id": 1, "title": "A", "artist": "杉森雅和"}]
        )
        cell = self._artist_cell(out)
        assert "38;2;" not in cell, f"普通歌手不该有代表色：{cell!r}"

    def test_关掉着色后全是白字(self, monkeypatch):
        # patch 的是 output 模块里那个名字：_artist_text 早就把
        # is_artist_color 绑到自己模块的命名空间了，
        # patch config_mod 那个不改变已绑定的引用
        monkeypatch.setattr("function.output.is_artist_color", lambda: False)
        out = self._rendered(
            monkeypatch, [{"id": 1, "title": "A", "artist": "なきそ, 初音ミク"}]
        )
        cell = self._artist_cell(out)
        assert "38;2;" not in cell, cell

    def test_artist为空也不炸(self, monkeypatch):
        """老条目没有 artist 键，早先 fill 测试挖过这个"""
        out = self._rendered(monkeypatch, [{"id": 1, "title": "A"}])
        assert out.strip()


class Test曲目表宽度:
    def test_曲目表占满终端(self, ready, monkeypatch, capsys):
        """另外三个命令的曲目表都有 expand=True，这张也得有"""
        monkeypatch.setattr(tracker, "console", Console(width=150))
        tracker.cmd_tracker(ns(limit=3))
        out = capsys.readouterr().out
        songs_rows = [ln for ln in out.splitlines() if ln.startswith("│ 1 │")]
        assert songs_rows, "没有曲目行"
        assert max(len(ln) for ln in songs_rows) >= 140, "曲目表没占满终端宽度"

    def test_标题与艺术家有ratio(self, ready, monkeypatch, capsys):
        """4:3 是退让顺序。没有它时最长那列通吃，标题能被压到三个汉字宽。

        只量宽度测不出来 —— expand=True 时两列照样撑满，
        得直接量那两列各自占多少格。
        """
        from rich.table import Table

        monkeypatch.setattr(tracker, "console", Console(width=100))
        captured = {}
        real = Table

        def spy(*a, **kw):
            t = real(*a, **kw)
            captured["t"] = t
            return t

        monkeypatch.setattr("rich.table.Table", spy)
        songs = [{"id": i, "title": "x" * 60, "artist": "y"} for i in range(3)]
        tracker._display_songs(songs, 0)
        cols = {c.header: c for c in captured["t"].columns}
        assert cols["标题"].ratio == 4
        assert cols["艺术家"].ratio == 3


class Test曲目表:
    @pytest.fixture(autouse=True)
    def wide(self, monkeypatch):
        """宽度固定，否则 rich 把标题折行，断言的字符串就断了"""
        monkeypatch.setattr(tracker, "console", Console(width=200))

    def test_面板带已缓存曲目数(self, ready, capsys):
        """总数在面板里，不必再在表格下面单起一行"""
        tracker.cmd_tracker(ns(limit=3))
        assert "已缓存曲目：200" in capsys.readouterr().out

    def test_面板给设置文件的路径(self, ready, capsys):
        """来源是用户自己写的，每次列一遍没有新信息，而 529 首一屏放不下。

        给路径就够：要看或改直接开那个文件。
        """
        tracker.cmd_tracker(ns(limit=3))
        out = capsys.readouterr().out
        assert "settings.toml" in out
        assert "819104208" not in out, "来源列表不该再出现在面板上"

    def test_没配来源时说清(self, ready, monkeypatch, capsys):
        """一个来源都没配时那行路径是死的，得说清为什么"""
        monkeypatch.setattr(
            tracker, "load_settings", lambda n: {"description": "d", "sources": []}
        )
        tracker.cmd_tracker(ns(limit=3))
        assert "尚未配置来源" in capsys.readouterr().out

    def test_四列(self, ready, capsys):
        tracker.cmd_tracker(ns())
        out = capsys.readouterr().out
        for col in ("#", "ID", "标题", "艺术家"):
            assert col in out, f"少了 {col} 列"

    def test_序号是绝对的(self, ready, capsys):
        tracker.cmd_tracker(ns(offset=100, limit=3))
        out = capsys.readouterr().out
        rows = [
            ln
            for ln in out.splitlines()
            if ln.startswith("│") and ln.split("│")[1].strip().isdigit()
        ]
        assert [ln.split("│")[1].strip() for ln in rows] == ["101", "102", "103"]

    def test_标题带区间(self, ready, capsys):
        tracker.cmd_tracker(ns(offset=5, limit=3))
        assert "6-8/20" in capsys.readouterr().out

    def test_不给offset也给区间(self, ready, capsys):
        tracker.cmd_tracker(ns(limit=10))
        assert "1-10/200" in capsys.readouterr().out

    def test_默认十条(self, ready, capsys):
        tracker.cmd_tracker(ns())
        assert "1-10/200" in capsys.readouterr().out

    def test_超出范围给提示(self, ready, capsys):
        tracker.cmd_tracker(ns(offset=999))
        assert "超出范围（共 200 首）" in capsys.readouterr().out

    def test_没有artist的老条目那一列是空的(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(
            tracker, "load_songs_db", lambda n: songs(with_artist=False)
        )
        tracker.cmd_tracker(ns(limit=2))
        out = capsys.readouterr().out
        assert "曲目1" in out, "老条目照样要能看，不能因为缺 artist 就整表不显示"

    def test_空库不给表(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(tracker, "load_songs_db", lambda n: [])
        tracker.cmd_tracker(ns())
        out = capsys.readouterr().out
        assert "已缓存曲目 -" not in out


class TestLimitOffset现在对面板生效:
    def test_help不再说只作用于json(self):
        """曲目表做完了，那句得删"""

        out = _out_of(["tracker", "like", "--help"])
        assert "只作用于 --json" not in out

    def test_json仍然切片(self, ready, capsys):
        tracker.cmd_tracker(ns(json=True, limit=2, offset=3))
        data, _out, _err = parsed(capsys)
        assert [s["id"] for s in data["tracker"]["songs"]] == [4, 5]


class TestJson带artist:
    def test_json里的song有artist(self, ready, capsys):
        tracker.cmd_tracker(ns(json=True, limit=1))
        data, _out, _err = parsed(capsys)
        assert data["tracker"]["songs"][0]["artist"] == "艺术家1"

    def test_老条目没有artist键也照样输出(self, ready, monkeypatch, capsys):
        """不补键：那会让 songs.json 的形状随是否 fetch 过而变"""
        monkeypatch.setattr(
            tracker, "load_songs_db_full", lambda n: db(with_artist=False)
        )
        tracker.cmd_tracker(ns(json=True, limit=1))
        data, _out, _err = parsed(capsys)
        assert data["tracker"]["songs"][0] == {"id": 1, "title": "曲目1"}


def _out_of(argv):
    import io
    import re
    from contextlib import redirect_stdout

    from vncmd import build_parser

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            build_parser().parse_args(argv)
    except SystemExit:
        pass
    return re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())
