"""时长格式与发行时间零后缀"""

import pytest

from vncmd.core.output import _trim_midnight
from vncmd.net.api import _fmt_duration


class TestDuration:
    @pytest.mark.parametrize(
        ("ms", "want"),
        [
            (None, ""),
            (0, ""),
            (1, "0:00"),
            (1_000, "0:01"),
            (1_000 * 59, "0:59"),
            (1_000 * 60, "1:00"),
            (1_000 * 60 + 1_000 * 4, "1:04"),
            (1_000 * 60 * 3 + 1_000 * 47, "3:47"),
            (1_000 * 60 * 9 + 1_000 * 59, "9:59"),
            (1_000 * 60 * 59 + 1_000 * 59, "59:59"),
        ],
    )
    def test_不足一小时保持原样(self, ms, want):
        assert _fmt_duration(ms) == want

    @pytest.mark.parametrize(
        ("ms", "want"),
        [
            (1_000 * 60 * 60, "1:00:00"),
            (1_000 * 60 * 95 + 1_000 * 4, "1:35:04"),
            (1_000 * 60 * 194 + 1_000 * 25, "3:14:25"),
            (1_000 * 60 * 60 * 10 + 1_000 * 1, "10:00:01"),
        ],
    )
    def test_超过一小时补出小时位(self, ms, want):
        assert _fmt_duration(ms) == want

    def test_整小时的边界(self):
        """59:59 之后就该进位，不能出现 60:00 这种写法"""
        assert _fmt_duration(1_000 * 60 * 60 - 1) == "59:59"
        assert _fmt_duration(1_000 * 60 * 60) == "1:00:00"

    def test_分与秒都要补零(self):
        assert _fmt_duration(1_000 * 60 * 61 + 1_000 * 5) == "1:01:05"
        assert _fmt_duration(1_000 * 60 * 3 + 1_000 * 5) == "3:05"

    def test_小时位不补零(self):
        """03:00:00 比 3:00:00 自然得多"""
        assert _fmt_duration(1_000 * 60 * 180) == "3:00:00"

    def test_毫秒截断到秒(self):
        assert _fmt_duration(1_000 * 60 * 3 + 1_000 * 47 + 999) == "3:47"

    def test_超小时只宽一格(self):
        """只有超过一小时的曲目宽一个字符，表格不受影响"""
        old = "194:25"
        new = _fmt_duration(1_000 * 60 * 194 + 1_000 * 25)
        assert new == "3:14:25"
        assert len(new) - len(old) == 1


class TestTrimMidnight:
    def test_零点只留日期(self):
        assert _trim_midnight("2022-03-14 00:00:00") == "2022-03-14"

    def test_非零点保留完整时间(self):
        assert _trim_midnight("2021-12-24 05:10:20") == "2021-12-24 05:10:20"

    def test_空串原样返回(self):
        assert _trim_midnight("") == ""

    def test_不会误伤看起来像零点但不是的(self):
        """只有结尾整段为 00:00:00 才裁，带毫秒或别的尾数都不能动"""
        assert _trim_midnight("2022-03-14 00:00:00.500") == "2022-03-14 00:00:00.500"
        assert _trim_midnight("2022-03-14 10:00:00") == "2022-03-14 10:00:00"

    def test_原始字符串不被就地修改(
        self,
    ):
        """它还要被 metadata.py 拿去写标签，就地改会连累那边"""
        original = "2022-03-14 00:00:00"
        _trim_midnight(original)
        assert original == "2022-03-14 00:00:00"

    def test_零时间戳在东八区不被裁(self):
        """publishTime 为 0 时东八区显示 08:00:00，不能当成零点裁掉"""
        assert _trim_midnight("1970-01-01 08:00:00") == "1970-01-01 08:00:00"

    def test_零时间戳在UTC下会被裁(self):
        assert _trim_midnight("1970-01-01 00:00:00") == "1970-01-01"
