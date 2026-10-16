"""check_md5 与 AudioSource 的行为"""

import hashlib

import pytest

from function.api import AudioSource
from function.checker import check_md5


@pytest.fixture
def sample(tmp_path):
    """写一个已知内容的文件，同时返回路径、md5 与大小"""
    data = b"vncmd" * 5000
    p = tmp_path / "sample.flac"
    p.write_bytes(data)
    return str(p), hashlib.md5(data).hexdigest(), len(data)


def test_md5_and_size_match(sample):
    path, md5, size = sample
    ok, msg = check_md5(path, md5, size)
    assert ok, msg
    assert msg == ""


def test_size_wrong_but_md5_right_passes(sample):
    """md5 对得上就放行，哪怕 size 字段本身不准

    宁可放过一次可疑的文件，也不能因为一个旁证字段错乱就拒掉完好的下载
    """
    path, md5, size = sample
    ok, msg = check_md5(path, md5, size + 1)
    assert ok, msg


def test_size_wrong_and_md5_wrong_reports_both(sample):
    """两道都不符时两条线索都要给，截断场景下大小差异最直观"""
    path, _md5, size = sample
    with open(path, "r+b") as f:
        f.truncate(size // 2)
    ok, msg = check_md5(path, "0" * 32, size)
    assert not ok
    assert "大小不符" in msg
    assert "md5 也不符" in msg
    assert str(size // 2) in msg


def test_size_wrong_without_md5_still_fails(sample):
    """没有 md5 可依时，size 是仅剩的依据，不符就得判失败"""
    path, _md5, size = sample
    ok, msg = check_md5(path, "", size + 1)
    assert not ok
    assert "大小不符" in msg
    assert str(size) in msg


def test_size_wrong_without_md5_skips_hashing(sample, monkeypatch):
    """只有 size 可比时不该去算 md5，那一步没有依据也没有意义"""
    path, _md5, size = sample

    def boom(*_args, **_kwargs):
        raise AssertionError("没有 md5 依据时不应计算哈希")

    monkeypatch.setattr(hashlib, "md5", boom)
    ok, _ = check_md5(path, "", size + 1)
    assert not ok


def test_md5_mismatch_reports_actual(sample):
    path, md5, size = sample
    ok, msg = check_md5(path, "0" * 32, size)
    assert not ok
    assert "md5 不符" in msg
    # 声明值与实际值都要在提示里，否则用户无从判断损坏程度
    assert md5[:7] in msg


def test_md5_mismatch_shows_prefix_only(sample):
    """不符时只展示前 7 位，全长摘要既占地方又看不出新信息"""
    path, md5, size = sample
    _ok, msg = check_md5(path, "0" * 32, size)
    assert f"{md5[:7]}..." in msg
    assert f"{'0' * 7}..." in msg
    # 完整摘要不该出现在提示里
    assert md5 not in msg


def test_short_digest_not_padded():
    """异常短的摘要不该被硬加省略号，那会把它伪装成正常长度"""
    from function.checker import _short_digest

    assert _short_digest("abc") == "abc"
    assert _short_digest("1234567") == "1234567"
    assert _short_digest("12345678") == "1234567..."
    assert _short_digest("820574c3c7185559957fcee1098b6912") == "820574c..."


def test_uppercase_expectation_accepted(sample):
    """服务端偶尔会给大写十六进制，不该因此判为不符"""
    path, md5, size = sample
    ok, msg = check_md5(path, md5.upper(), size)
    assert ok, msg


def test_no_expectation_passes_without_reading(sample):
    """两个期望值都缺时直接放行，不该去碰文件"""
    path, _md5, _size = sample
    ok, msg = check_md5(path, "", 0)
    assert ok
    assert msg == ""


def test_size_only_skips_md5(sample):
    """只给了 size 时核对完就收工，不做 md5"""
    path, _md5, size = sample
    ok, msg = check_md5(path, "", size)
    assert ok, msg


def test_truncated_file_fails_size_check(sample):
    """下载中断留下的半截文件应被挡下"""
    path, md5, size = sample
    with open(path, "r+b") as f:
        f.truncate(size // 2)
    ok, msg = check_md5(path, md5, size)
    assert not ok
    assert "大小不符" in msg


def test_same_size_different_content_fails_md5(sample):
    """大小相同但内容被换掉，只能靠 md5 发现"""
    path, _md5, size = sample
    with open(path, "r+b") as f:
        f.seek(0)
        f.write(b"XXXX")
    ok, msg = check_md5(path, _md5, size)
    assert not ok
    assert "md5 不符" in msg


def test_large_file_hashed_in_blocks(tmp_path):
    """分块读取要能正确处理跨块边界"""
    data = bytes(range(256)) * 20000  # 约 5 MB，整除 1 MB 块大小
    p = tmp_path / "big.mp3"
    p.write_bytes(data)
    ok, msg = check_md5(str(p), hashlib.md5(data).hexdigest(), len(data))
    assert ok, msg


def test_audio_source_defaults_are_usable():
    """缺失字段要退化成 0 与空串，而不是 None 引发下游报错"""
    src = AudioSource("http://example.com/a.flac")
    assert src.url == "http://example.com/a.flac"
    assert src.size == 0
    assert src.md5 == ""
    assert src.expi == 0


def test_audio_source_keeps_all_fields():
    src = AudioSource("http://x/a.flac", 26995264, "820574c3c718", 1200)
    assert (src.url, src.size, src.md5, src.expi) == (
        "http://x/a.flac",
        26995264,
        "820574c3c718",
        1200,
    )
