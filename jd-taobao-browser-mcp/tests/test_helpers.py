from jd_taobao_mcp.extractors.helpers import compact_text, parse_price
from jd_taobao_mcp.service import platform_from_url


def test_parse_price():
    assert parse_price("¥1,299.00") == 1299.0
    assert parse_price("￥88") == 88.0
    assert parse_price("暂无报价") is None


def test_compact_text():
    assert compact_text(" a\n  b \t c ") == "a b c"


def test_platform_from_url():
    assert platform_from_url("https://item.jd.com/1.html") == "jd"
    assert platform_from_url("https://item.taobao.com/item.htm?id=1") == "taobao"
    assert platform_from_url("https://detail.tmall.com/item.htm?id=1") == "taobao"
