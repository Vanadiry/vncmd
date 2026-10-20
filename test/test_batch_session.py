"""下载会话准备、并发环境与收尾打印"""

from pathlib import Path
from queue import Empty
from types import SimpleNamespace

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
        # 形如 2026-10-18_15-43-09，下划线在第 11 位
        stamp = Path(session_dir).name
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
        assert warns and "重新开始下载" in warns[0]

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
        """用户分不清“没成功”与“没打印”"""
        out = self._跑(capsys, 0, 0)
        assert "0 成功" in out and "0 失败" in out

    def test_有失败ID才列ID(self, capsys):
        assert "失败 ID" not in self._跑(capsys, 3, 0)
        assert "失败 ID" not in self._跑(capsys, 0, 1)

    def test_列失败ID(self, capsys):
        out = self._跑(capsys, 3, 2, [101, 103])
        assert "失败 ID：101，103" in out

    def _原始输出(self, monkeypatch, ok, fail, ids=()):
        """收 rich 打印前的原始字符串，capsys 拿不到标记
        开头那个空行来自零参数调用，所以用 extend 而不用 append
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
        """0 暗示“本来就没有”，不必醒目，两个方向都要 dim"""
        全部 = self._原始输出(monkeypatch, 0, 0)
        assert "[dim]0 成功[/]" in 全部
        assert "[dim]0 失败[/]" in 全部
        assert "[green]" not in 全部
        assert "[red]" not in 全部


class Test并发环境准备:
    """槽位数与提交的 worker 数必须相等
    多提交一个 worker 会让那一首随线程消失，成功失败都不计入
    """

    def _tracks(self, n):
        return [{"id": 100 + i, "title": f"歌{i}", "artist": "人"} for i in range(n)]

    def test_并发数大于曲目数时按曲目数开槽(self):
        workers = downloader._prepare_workers(self._tracks(3), 8)
        assert workers.count == 3
        assert len(workers.slots) == workers.count

    def test_并发数小于曲目数时按并发数开槽(self):
        workers = downloader._prepare_workers(self._tracks(20), 4)
        assert workers.count == 4
        assert len(workers.slots) == workers.count

    def test_槽位数永远等于worker数(self):
        """这条用例盯住静默丢歌的约束"""
        for 曲目数 in (1, 2, 3, 7, 16):
            for 并发 in (1, 2, 4, 8, 16):
                workers = downloader._prepare_workers(self._tracks(曲目数), 并发)
                assert len(workers.slots) == workers.count, (
                    f"{曲目数} 首配 {并发} 并发时对不上"
                )
                assert workers.count == min(并发, 曲目数)

    def test_曲目全部装进队列(self):
        workers = downloader._prepare_workers(self._tracks(5), 2)
        剩下的 = []
        while True:
            try:
                剩下的.append(workers.queue.get_nowait())
            except Empty:
                break
        assert [t["id"] for t in 剩下的] == [100, 101, 102, 103, 104]

    def test_每个槽位起始时不可见(self):
        """不可见的槽位不占进度条的一行，空闲时不该刷屏"""
        workers = downloader._prepare_workers(self._tracks(3), 3)
        for task_id in workers.slots:
            assert workers.progress.tasks[task_id].visible is False

    def test_show让槽位可见(self):
        workers = downloader._prepare_workers(self._tracks(1), 1)
        task_id = workers.slots[0]
        workers.show(task_id)
        assert workers.progress.tasks[task_id].visible is True

    def test_release让槽位回到不可见且清空描述(self):
        workers = downloader._prepare_workers(self._tracks(1), 1)
        task_id = workers.slots[0]
        workers.show(task_id)
        workers.describe(task_id, "歌0 - 人")
        assert "歌0" in str(workers.progress.tasks[task_id].description)
        workers.release(task_id)
        assert workers.progress.tasks[task_id].visible is False
        assert str(workers.progress.tasks[task_id].description).strip() == ""

    def test_restart只清总长不藏槽位(self):
        """重试同一首时槽位必须留着可见，藏了就没法再显出来
        describe 只写描述，不会把 visible 设回 True
        """
        workers = downloader._prepare_workers(self._tracks(1), 1)
        task_id = workers.slots[0]
        workers.show(task_id)
        workers.progress.update(task_id, total=100, completed=40)
        workers.restart(task_id)
        assert workers.progress.tasks[task_id].visible is True
        # total 保持原值、completed 归零，下一轮下载会按新的总长重设
        assert workers.progress.tasks[task_id].completed == 0

    def test_restart之后还能继续写描述(self):
        """重试、写提示、下载推进进度这条路径"""
        workers = downloader._prepare_workers(self._tracks(1), 1)
        task_id = workers.slots[0]
        workers.show(task_id)
        workers.progress.update(task_id, total=100, completed=40)
        workers.restart(task_id)
        workers.describe(task_id, "歌0 - 人，重试 1/3")
        assert workers.progress.tasks[task_id].visible is True
        assert "重试 1/3" in str(workers.progress.tasks[task_id].description)

    def test_describe带_markup转义(self):
        """歌名里的方括号会被 rich 当成样式标记，描述里要带反斜杠转义"""
        workers = downloader._prepare_workers(self._tracks(1), 1)
        task_id = workers.slots[0]
        workers.describe(task_id, "歌[live] - 人")
        assert "\\[live]" in str(workers.progress.tasks[task_id].description)

    def test_零首时开零个槽(self):
        workers = downloader._prepare_workers([], 4)
        assert workers.count == 0
        assert workers.slots == []


class Test取链接重试:
    """三次都取不到就返回 None，不抛
    取不到链接属常态，调用方要按这一首失败处理，不中断整批
    """

    def _打桩(self, monkeypatch, 每次返回):
        """按列表轮流返回，取完后复用最后一个"""
        记录 = []

        def 取(_sid, quality=None):
            i = min(len(记录), len(每次返回) - 1)
            记录.append(每次返回[i])
            return 每次返回[i]

        monkeypatch.setattr(downloader, "get_audio_source", 取)
        return 记录

    def _假音源(self):
        return SimpleNamespace(url="http://x/a.flac", size=1, md5="", level="lossless")

    def test_第一次就拿到就只调一次(self, monkeypatch):
        音源 = self._假音源()
        记录 = self._打桩(monkeypatch, [音源])
        assert downloader._fetch_source_with_retry(1, 999) is 音源
        assert len(记录) == 1

    def test_第二次拿到就调两次(self, monkeypatch):
        音源 = self._假音源()
        记录 = self._打桩(monkeypatch, [None, 音源])
        assert downloader._fetch_source_with_retry(1, 999) is 音源
        assert len(记录) == 2

    def test_三次都拿不到返回None(self, monkeypatch):
        记录 = self._打桩(monkeypatch, [None, None, None])
        assert downloader._fetch_source_with_retry(1, 999) is None
        assert len(记录) == downloader._LINK_ATTEMPTS

    def test_不会无限重试(self, monkeypatch):
        """永远取不到也只能试三次，上游返回空 url 时不会卡死批次"""
        记录 = self._打桩(monkeypatch, [None])
        downloader._fetch_source_with_retry(1, 999)
        assert len(记录) == downloader._LINK_ATTEMPTS

    def test_on_retry只在还有下一次时调用(self, monkeypatch):
        """最后一次失败之后不再提示重试，那样会显示“重试 3/3”却不再重试"""
        次数 = []
        self._打桩(monkeypatch, [None, None, None])
        downloader._fetch_source_with_retry(1, 999, 次数.append)
        assert 次数 == [1, 2]

    def test_成功那次不调_on_retry(self, monkeypatch):
        次数 = []
        音源 = self._假音源()
        self._打桩(monkeypatch, [音源])
        downloader._fetch_source_with_retry(1, 999, 次数.append)
        assert 次数 == []

    def test_没有_on_retry也能跑(self, monkeypatch):
        self._打桩(monkeypatch, [None, None, None])
        assert downloader._fetch_source_with_retry(1, 999) is None

    def test_音质原样传下去(self, monkeypatch):
        """quality 为码率，重试之间不能丢掉或写死"""
        看到的 = []
        音源 = self._假音源()

        def 取(_sid, quality=None):
            看到的.append(quality)
            return 音源

        monkeypatch.setattr(downloader, "get_audio_source", 取)
        downloader._fetch_source_with_retry(1, 320000)
        assert 看到的 == [320000]


class Test槽位方法的调用点:
    """直接读源码钉住 worker 循环里的方法调用，循环在 _download_one 闭包里
    重试同一首用了 release 会让那一路进度一直不可见
    """

    def _源码(self):
        # 按相对路径找，写死绝对路径换个机器就跑不了
        return Path("src/vncmd/downloader.py").read_text(encoding="utf-8")

    def _重试那一段(self):
        """从最后一次 download_song 调用截到 if attempt < 3
        上界不能取 release，解析失败那处 release 排在重试循环之前，会截掉整段重试
        """
        源码 = self._源码()
        起 = 源码.rindex("ok, msg, _ = download_song(")
        止 = 源码.index("if attempt < 3:", 起)
        return 源码[起:止]

    def test_重试处必须调restart(self):
        段 = self._重试那一段()
        assert "workers.restart(task_id)" in 段
        assert "workers.release(task_id)" not in 段, (
            "重试同一首不能释放槽位，否则那一路进度就此静默"
        )

    def test_每首处理完要释放槽位(self):
        """全文件 release 与 restart 的调用点数要对得上方法数
        少调 release 槽位不回收，多调 release 会让重试静默
        """
        源码 = self._源码()
        assert 源码.count("workers.release(task_id)") == 4
        assert 源码.count("workers.restart(task_id)") == 1
