"""下载结果各行箭头对齐"""

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from rich.cells import cell_len

from vncmd import downloader


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1, 1), (255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


AUDIO = b"fLaC" + b"vncmd" * 5000
LYRIC = "[00:00.00] 词\n[00:03.00] 曲"
COVER = _png()


def arrow_column(line: str) -> int:
    """箭头所在的显示列，按显示宽度算而不是字符数"""
    return cell_len(line.split("→")[0] + "→")


@pytest.fixture
def song(tmp_path, monkeypatch):
    """跑一次 download_song，返回它给出的结果文本与当前配置状态"""
    state = {"content": "alc", "lyrics": (LYRIC, "")}

    def fake_fetch(url, path, label, progress=None, task_id=None, **kw):
        # fetch_audio 的约定为“错误说明或 None”，写成功不能返回字节数
        Path(path).write_bytes(AUDIO)

    monkeypatch.setattr(downloader, "fetch_audio", fake_fetch)
    monkeypatch.setattr(downloader, "fetch_lyrics", lambda *_a: state["lyrics"])
    monkeypatch.setattr(downloader, "fetch_cover", lambda *_a: COVER)
    monkeypatch.setattr(downloader, "embed_metadata", lambda *_a: None)
    monkeypatch.setattr(downloader, "get_check_enabled", lambda: False)
    monkeypatch.setattr(downloader, "get_download_content", lambda: state["content"])

    def run(title="歌", artist="人", lyrics=(LYRIC, "")):
        state["lyrics"] = lyrics
        ok, msg, _ = downloader.download_song(
            song_url="http://x/a.flac",
            song_title=title,
            song_artist=artist,
            song_album="专",
            song_id=1,
            cover_url="http://x/c.png",
            lyrics_api_url="http://x/l",
            publish_time="",
            download_dir=str(tmp_path / f"d{abs(hash(title)) % 1000}"),
            song_md5=hashlib.md5(AUDIO).hexdigest(),
        )
        return ok, msg

    run.state = state
    return run


class TestArrowAlignment:
    def test_三行箭头同列(self, song):
        ok, msg = song()
        assert ok, msg
        cols = [arrow_column(line) for line in msg.splitlines()]
        assert len(cols) == 3, f"行数不对：{msg}"
        assert len(set(cols)) == 1, f"箭头没对齐，各行在第 {cols} 列"

    def test_补齐按显示宽度而非字符数(self, song):
        """“封面”两个汉字占四格，和 FLAC 一样宽，按字符数补就会错开一格"""
        _ok, msg = song()
        by_label = {line.split()[0]: line for line in msg.splitlines()}
        assert set(by_label) == {"音频", "歌词", "封面"}
        assert arrow_column(by_label["音频"]) == arrow_column(by_label["封面"])
        assert arrow_column(by_label["歌词"]) == arrow_column(by_label["音频"])

    def test_mp3_也能对齐(self, song, monkeypatch):
        """MP3 只有三格，比 FLAC 窄，要补空格而不是原样输出"""
        monkeypatch.setattr(downloader, "get_type_from_url", lambda _u: "mp3")
        _ok, msg = song()
        cols = {arrow_column(line) for line in msg.splitlines()}
        assert len(cols) == 1, f"箭头没对齐：{msg}"

    def test_出现完整名字时按最宽的补(self, song):
        """完整名字占八格，会成为本次输出里最宽的标签"""
        _ok, msg = song(title="超长歌名" * 40)
        assert "完整名字" in msg
        cols = {arrow_column(line) for line in msg.splitlines() if "→" in line}
        assert len(cols) == 1, f"箭头没对齐：{msg}"

    def test_补齐只动标签不动内容(self, song):
        """文件名一个都不能变，标签与箭头之间只该有一个空格"""
        _ok, msg = song()
        lines = msg.splitlines()
        assert lines[0] == '音频 → "歌 - 人.flac"'
        assert lines[1] == '歌词 → "歌 - 人.lrc"'
        assert lines[2] == '封面 → "歌 - 人.png"'
        for line in lines:
            head = line.split("→")[0]
            assert head == f"{head.strip()} ", f"标签后不止一个空格：{line}"
        # 绝对列号随箭头字符的宽度而定，只断言各行落在同一列
        assert len({arrow_column(line) for line in lines}) == 1

    def test_音频行没有类型时不留箭头(self, song, monkeypatch):
        """类型为空时整行只有文件名，补齐不能凭空造出箭头"""
        monkeypatch.setattr(downloader, "get_type_from_url", lambda _u: "")
        _ok, msg = song()
        first = msg.splitlines()[0]
        assert "→" not in first, f"无类型时不该有箭头：{first}"
        assert first.startswith('"') and first.endswith('"')
        # 其余各行仍要照常对齐
        rest = [arrow_column(line) for line in msg.splitlines()[1:]]
        assert len(set(rest)) == 1

    def test_什么都没下时报原有错误(self, song):
        song.state["content"] = "l"
        ok, msg = song(lyrics=("", ""))
        assert not ok
        assert "未下载任何内容" in msg
