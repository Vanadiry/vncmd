from test.conftest import SAMPLE_MS, as_tz
from vncmd.net import api as api_mod

SHANGHAI_STR = "2011-09-01 16:00:00"


def test_毫秒时间戳转上海时间字符串():
    with as_tz("UTC"):
        assert api_mod._fmt_publish_time(SAMPLE_MS) == SHANGHAI_STR


def test_进程时区不影响结果():
    """发行时间固定按上海算，CI 在 UTC 上也要得到同一个日期"""
    with as_tz("Asia/Shanghai"):
        cn = api_mod._fmt_publish_time(SAMPLE_MS)
    with as_tz("UTC"):
        utc = api_mod._fmt_publish_time(SAMPLE_MS)
    assert cn == SHANGHAI_STR
    assert utc == SHANGHAI_STR


def test_1990年夏令时按上海算():
    # 1990 年上海实行夏令时 UTC+9，固定 +8 会落到前一天
    with as_tz("UTC"):
        assert api_mod._fmt_publish_time(646758000000) == "1990-07-01 00:00:00"


def test_零时间戳按无日期处理():
    with as_tz("UTC"):
        assert api_mod._fmt_publish_time(0) == ""


def test_拿不到时间戳返回空串():
    # 返回 None 会让下游 strptime 炸，返回空串才会被 if publish_time 跳过
    assert api_mod._fmt_publish_time(None) == ""


def test_按毫秒解释():
    # 网易云给的是毫秒，当秒解释会把 2011 年的日期落到 1970 年 1 月中旬
    with as_tz("UTC"):
        ms = api_mod._fmt_publish_time(SAMPLE_MS)
        sec = api_mod._fmt_publish_time(1314864000)
    assert ms == SHANGHAI_STR
    assert sec != ms


def test_毫秒部分被截断到秒():
    # 同一秒内的两个时间戳要格式化出同一个结果，否则元数据里的发行时间会抖
    assert api_mod._fmt_publish_time(1758000000123) == api_mod._fmt_publish_time(
        1758000000999
    )


def test_格式为秒级精度():
    out = api_mod._fmt_publish_time(1758000000123)
    assert len(out) == 19
    assert out[4] == "-" and out[7] == "-" and out[10] == " "
    assert out[13] == ":" and out[16] == ":"


def test_与_fmt_duration同属私有格式化函数():
    # api.py 的格式化函数统一 _ 前缀，format_timestamp 当初漏了
    assert api_mod._fmt_publish_time.__name__.startswith("_")
    assert api_mod._fmt_duration.__name__.startswith("_")


def test_不再有旧的公开名():
    assert not hasattr(api_mod, "format_timestamp")
