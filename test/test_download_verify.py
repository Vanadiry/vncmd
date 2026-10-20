"""下载落盘与逐道校验"""

import hashlib
from pathlib import Path

import pytest

from vncmd import downloader


@pytest.fixture
def 假下载(monkeypatch, tmp_path):
    """把 fetch_audio 换成写指定大小的文件，并记录路径与内容"""
    记录 = []

    def 装(大小=1024, 内容=None, 报错=None):
        def fetch(url, path, label, **kw):
            记录.append({"路径": path, "标签": label, "大小": 大小})
            if 报错:
                # 真实下载失败时也会留下半截文件
                Path(path).write_bytes(b"partial")
                return 报错
            Path(path).write_bytes(内容 if 内容 is not None else b"x" * 大小)
            return None

        monkeypatch.setattr(downloader, "fetch_audio", fetch)
        return 记录

    return 装


@pytest.fixture
def 不解码(monkeypatch):
    monkeypatch.setattr(downloader, "any_check_tool", lambda: False)


def _跑(tmp_path, **kw):
    return downloader._download_and_verify(
        str(tmp_path / "1.flac"),
        song_url="http://x/a.flac",
        label="歌 - 人",
        song_size=kw.pop("song_size", 0),
        song_md5=kw.pop("song_md5", ""),
        **kw,
    )


class Test成功:
    def test_三道都过返回None(self, 假下载, tmp_path, 不解码):
        假下载()
        assert _跑(tmp_path) is None
        assert (tmp_path / "1.flac").read_bytes() == b"x" * 1024

    def test_标签传给下载层(self, 假下载, tmp_path, 不解码):
        记录 = 假下载()
        _跑(tmp_path)
        assert 记录[0]["标签"] == "歌 - 人"


class Test下载本身失败:
    def test_报错带在消息里(self, 假下载, tmp_path, 不解码):
        假下载(报错="连接被重置")
        错 = _跑(tmp_path)
        assert 错 == "下载失败：连接被重置"

    def test_半截文件要删掉(self, 假下载, tmp_path, 不解码):
        """留着会占着 _temp 里的同名位置，下一首同 id 的歌重下会撞上"""
        假下载(报错="连接被重置")
        _跑(tmp_path)
        assert not (tmp_path / "1.flac").exists()


class Test下载为空:
    def test_空文件判失败(self, 假下载, tmp_path, 不解码):
        假下载(大小=0)
        assert _跑(tmp_path) == "下载文件为空"

    def test_空文件要删掉(self, 假下载, tmp_path, 不解码):
        假下载(大小=0)
        _跑(tmp_path)
        assert not (tmp_path / "1.flac").exists()

    def test_只有换行不算空(self, 假下载, tmp_path, 不解码):
        """判“有没有内容”，与纯文本歌词判时间戳的口径不同"""
        假下载(内容=b"\n")
        assert _跑(tmp_path) is None


class Testmd5:
    def test_对得上就过(self, 假下载, tmp_path, 不解码):
        内容 = b"hello"
        假下载(内容=内容)
        assert _跑(tmp_path, song_md5=hashlib.md5(内容).hexdigest()) is None

    def test_对不上判失败(self, 假下载, tmp_path, 不解码):
        假下载(内容=b"hello")
        错 = _跑(tmp_path, song_md5="0" * 32)
        assert "完整性校验失败" in 错

    def test_对不上要删掉文件(self, 假下载, tmp_path, 不解码):
        假下载(内容=b"hello")
        _跑(tmp_path, song_md5="0" * 32)
        assert not (tmp_path / "1.flac").exists()

    def test_没给md5就不查(self, 假下载, tmp_path, 不解码):
        """上游没给校验依据时跳过 md5，不能凭空判失败"""
        假下载(内容=b"hello")
        assert _跑(tmp_path, song_md5="") is None


class Test解码校验:
    def test_解码不通过要删掉文件(self, 假下载, tmp_path, monkeypatch):
        假下载()
        monkeypatch.setattr(downloader, "any_check_tool", lambda: True)
        monkeypatch.setattr(
            downloader, "check_audio", lambda p: (False, "解码错误: boom")
        )
        错 = _跑(tmp_path, run_check=True)
        assert "完整性校验失败" in 错 and "boom" in 错
        assert not (tmp_path / "1.flac").exists()

    def test_run_check为False就跳过解码(self, 假下载, tmp_path, monkeypatch):
        假下载()
        called = []
        monkeypatch.setattr(downloader, "any_check_tool", lambda: True)
        monkeypatch.setattr(downloader, "check_audio", lambda p: called.append(p))
        assert _跑(tmp_path, run_check=False) is None
        assert called == []

    def test_没有校验工具时跳过解码(self, 假下载, tmp_path, monkeypatch):
        """只装了 ffprobe 时 check_audio 拿不到可比对的结果，白跑还给出假的通过"""
        假下载()
        called = []
        monkeypatch.setattr(downloader, "any_check_tool", lambda: False)
        monkeypatch.setattr(downloader, "check_audio", lambda p: called.append(p))
        assert _跑(tmp_path, run_check=True) is None
        assert called == []

    def test_run_check为None时读配置(self, 假下载, tmp_path, monkeypatch):
        假下载()
        看到 = []
        monkeypatch.setattr(downloader, "get_check_enabled", lambda: True)
        monkeypatch.setattr(downloader, "any_check_tool", lambda: True)
        monkeypatch.setattr(
            downloader, "check_audio", lambda p: 看到.append(p) or (True, "")
        )
        assert _跑(tmp_path) is None
        assert 看到, "run_check 为 None 时该去读配置而不是当作关掉"


class Test封面处理:
    def test_没有封面数据时三样都是None(self):
        assert downloader._process_cover(None, "http://x/c.png") == (None, None, None)

    def test_正常时分成两份(self, monkeypatch):
        假封面 = b"\x89PNG" * 10

        def 处理(数据, url, compress):
            return (数据 + b"-embed", "image/png") if compress else (数据, "image/png")

        monkeypatch.setattr(downloader, "process_cover_image", 处理)
        embed, mime, save = downloader._process_cover(假封面, "http://x/c.png")
        assert embed == 假封面 + b"-embed"
        assert mime == "image/png"
        assert save == 假封面

    def test_封面坏了不连累音频(self, monkeypatch):
        """封面坏了降级为不嵌封面并出声告知，不能让整首失败"""

        def 炸(*_a, **_k):
            raise ValueError("图片文件已损坏")

        说了 = []
        monkeypatch.setattr(downloader, "process_cover_image", 炸)
        monkeypatch.setattr(downloader, "warning", 说了.append)
        assert downloader._process_cover(b"\x89PNG", "http://x/c.png") == (
            None,
            None,
            None,
        )
        assert 说了 and "封面处理失败" in 说了[0]
