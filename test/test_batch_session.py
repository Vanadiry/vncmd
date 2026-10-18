"""download_song_batch 里会话目录与收尾打印两块

这两块以前埋在函数中间，抽出来之后能直接测 —— 全是文件与断点操作，
一条都不用联网。之前它们跟着整个批次一起没被测到，
而 download_song_batch 的覆盖率长期只有 50%
"""

from pathlib import Path

from vncmd import downloader, session


def _tracks(n):
    return [{"id": 100 + i, "title": f"歌{i}", "artist": "人"} for i in range(n)]


class Test无断点时新建目录:
    def test_不给dl_type就全新下载(self, tmp_path):
        session_dir, selected, offset = session._setup_session(
            _tracks(3), str(tmp_path), None, None, None, 0
        )
        assert Path(session_dir).is_dir()
        assert Path(session_dir).parent == tmp_path
        assert [t["id"] for t in selected] == [100, 101, 102]
        assert offset == 0

    def test_目录名是时间戳(self, tmp_path):
        session_dir, _, _ = session._setup_session(
            _tracks(1), str(tmp_path), None, None, None, 0
        )
        # 形如 2026-10-18_15-43-09
        stamp = Path(session_dir).name
        # 形如 2026-10-18_21-25-38：日期十位是下划线，不是第 13 位
        assert len(stamp) == 19
        assert stamp[10] == "_"
        assert stamp[4] == stamp[7] == "-"

    def test_切片只取指定的一段(self, tmp_path):
        _, selected, offset = session._setup_session(
            _tracks(10), str(tmp_path), None, None, 3, 2
        )
        assert [t["id"] for t in selected] == [102, 103, 104]
        assert offset == 2

    def test_limit比总数还多时切出全量(self, tmp_path):
        _, selected, offset = session._setup_session(
            _tracks(3), str(tmp_path), None, None, 99, 0
        )
        assert len(selected) == 3
        assert offset == 0

    def test_空曲目表也能建目录(self, tmp_path):
        session_dir, selected, _ = session._setup_session(
            [], str(tmp_path), None, None, None, 0
        )
        assert Path(session_dir).is_dir()
        assert selected == []


class Test续传:
    def _断点(self, monkeypatch, session_dir):
        monkeypatch.setattr(
            session, "load_checkpoint", lambda *_a: {"download_dir": session_dir}
        )

    def test_目录还在就沿用(self, tmp_path, monkeypatch):
        旧的 = tmp_path / "上一轮"
        旧的.mkdir()
        self._断点(monkeypatch, str(旧的))
        monkeypatch.setattr(session, "sync_checkpoint_tracks", lambda *_a: ([], False))
        session_dir, _, _ = session._setup_session(
            _tracks(3), str(tmp_path), "playlist", "p1", None, 0
        )
        assert session_dir == str(旧的)

    def test_目录丢了就重新开始(self, tmp_path, monkeypatch):
        self._断点(monkeypatch, str(tmp_path / "早没了"))
        session_dir, _, _ = session._setup_session(
            _tracks(3), str(tmp_path), "playlist", "p1", None, 0
        )
        assert session_dir != str(tmp_path / "早没了")
        assert Path(session_dir).is_dir()

    def test_目录在本次输出目录之外要拦下(self, tmp_path, monkeypatch):
        """沿用它会让文件落到用户没有指定的位置，而用户拿不到任何提示"""
        本次 = tmp_path / "本次"
        本次.mkdir()
        别处 = tmp_path / "别处"
        别处.mkdir()
        self._断点(monkeypatch, str(别处))
        warns = []
        monkeypatch.setattr(session, "warning", lambda s: warns.append(s))
        session_dir, _, _ = session._setup_session(
            _tracks(3), str(本次), "playlist", "p1", None, 0
        )
        assert session_dir != str(别处)
        assert warns and "将重新开始下载" in warns[0]

    def test_续传时清掉上轮的半截_temp(self, tmp_path, monkeypatch):
        旧的 = tmp_path / "上一轮"
        (旧的 / "_temp").mkdir(parents=True)
        半截 = 旧的 / "_temp" / "123.flac"
        半截.write_bytes(b"partial")
        self._断点(monkeypatch, str(旧的))
        monkeypatch.setattr(session, "sync_checkpoint_tracks", lambda *_a: ([], False))
        session._setup_session(_tracks(3), str(tmp_path), "playlist", "p1", None, 0)
        assert not 半截.exists(), "上轮的半截文件要清掉，否则重下会撞同名"
        assert (旧的 / "_temp").is_dir()

    def test_全新下载不动别的_temp(self, tmp_path, monkeypatch):
        """没有断点时不该去动任何 _temp，只有续传才清"""
        monkeypatch.setattr(session, "load_checkpoint", lambda *_a: None)
        别人的 = tmp_path / "别人的" / "_temp"
        别人的.mkdir(parents=True)
        (别人的 / "x").write_bytes(b"x")
        session._setup_session(_tracks(3), str(tmp_path), "playlist", "p1", None, 0)
        assert (别人的 / "x").exists()

    def test_断点为空就是全新下载(self, tmp_path, monkeypatch):
        monkeypatch.setattr(session, "load_checkpoint", lambda *_a: None)
        seen = []
        monkeypatch.setattr(session, "create_checkpoint", lambda *a: seen.append(a))
        session_dir, _, _ = session._setup_session(
            _tracks(3), str(tmp_path), "album", "a1", None, 0
        )
        assert Path(session_dir).is_dir()
        assert seen, "全新下载要建断点，否则下次不知道从哪续"


class Test断点与切片的配合:
    """切片只影响本次下哪几首，断点仍记录全部曲目"""

    def test_断点记全量(self, tmp_path, monkeypatch):
        monkeypatch.setattr(session, "load_checkpoint", lambda *_a: None)
        seen = []
        monkeypatch.setattr(session, "create_checkpoint", lambda *a: seen.append(a))
        tracks = _tracks(10)
        session._setup_session(tracks, str(tmp_path), "playlist", "p1", 3, 0)
        assert sorted(seen[0][3]) == [t["id"] for t in tracks]

    def test_续传时按断点过滤(self, tmp_path, monkeypatch):
        旧的 = tmp_path / "上一轮"
        旧的.mkdir()
        monkeypatch.setattr(
            session, "load_checkpoint", lambda *_a: {"download_dir": str(旧的)}
        )
        monkeypatch.setattr(
            session,
            "sync_checkpoint_tracks",
            lambda *_a: (["101", "103"], False),
        )
        _, selected, _ = session._setup_session(
            _tracks(6), str(tmp_path), "playlist", "p1", None, 0
        )
        assert [t["id"] for t in selected] == [101, 103], "下过的要从这批里剔掉"

    def test_切片与断点过滤叠在一起(self, tmp_path, monkeypatch):
        """切片在前、断点过滤在后，所以两条会同时生效"""
        旧的 = tmp_path / "上一轮"
        旧的.mkdir()
        monkeypatch.setattr(
            session, "load_checkpoint", lambda *_a: {"download_dir": str(旧的)}
        )
        monkeypatch.setattr(
            session, "sync_checkpoint_tracks", lambda *_a: (["101", "105"], False)
        )
        _, selected, offset = session._setup_session(
            _tracks(6), str(tmp_path), "playlist", "p1", 3, 1
        )
        # 切片先取 1..3 即 101/102/103，再与断点取交集只剩 101
        assert [t["id"] for t in selected] == [101]
        assert offset == 1


class Test收尾打印:
    def _跑(self, capsys, ok, fail, ids=()):
        session._summarize(ok, fail, list(ids))
        return capsys.readouterr().err

    def test_全成功(self, capsys):
        out = self._跑(capsys, 3, 0)
        assert "3 成功" in out
        assert "0 失败" in out

    def test_全失败(self, capsys):
        out = self._跑(capsys, 0, 2)
        assert "0 成功" in out
        assert "2 失败" in out

    def test_一半一半(self, capsys):
        out = self._跑(capsys, 5, 2)
        assert "5 成功" in out and "2 失败" in out

    def test_零首也要说出来(self, capsys):
        """用户分不清「没成功」与「没打印」"""
        out = self._跑(capsys, 0, 0)
        assert "0 成功" in out and "0 失败" in out

    def test_有失败ID才列ID(self, capsys):
        assert "失败 ID" not in self._跑(capsys, 3, 0)
        assert "失败 ID" not in self._跑(capsys, 0, 1)

    def test_列失败ID(self, capsys):
        out = self._跑(capsys, 3, 2, [101, 103])
        assert "失败 ID：101, 103" in out

    def _原始输出(self, monkeypatch, ok, fail, ids=()):
        """收 rich 打印前的原始字符串

        直接读 capsys 拿不到标记 —— rich 打印时就把 [dim] 渲染掉了。
        开头那个空行是零参数调用，所以用 extend 而不是 append
        """
        收到的 = []
        monkeypatch.setattr(
            downloader.err_console, "print", lambda *a: 收到的.extend(a)
        )
        session._summarize(ok, fail, list(ids))
        return " ".join(收到的)

    def test_成功那档用green(self, monkeypatch):
        全部 = self._原始输出(monkeypatch, 3, 2)
        assert "[green]3 成功[/]" in 全部
        assert "[dim]0 成功[/]" not in 全部, "有成功就不该再报 0"

    def test_失败那档用red(self, monkeypatch):
        全部 = self._原始输出(monkeypatch, 3, 2)
        assert "[red]2 失败[/]" in 全部

    def test_零的那档走dim(self, monkeypatch):
        """0 暗示「本来就没有」，不必醒目 —— 两个方向都要dim"""
        全部 = self._原始输出(monkeypatch, 0, 0)
        assert "[dim]0 成功[/]" in 全部
        assert "[dim]0 失败[/]" in 全部
        assert "[green]" not in 全部
        assert "[red]" not in 全部
