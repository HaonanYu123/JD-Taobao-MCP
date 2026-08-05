from jd_taobao_mcp.extractors.helpers import compact_text, parse_price
from jd_taobao_mcp.service import _apply_detail_output_contract, platform_from_url


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


def test_detail_output_contract_targets():
    detail = {
        "url": "https://item.jd.com/1.html",
        "product_parameters": [{"name": "品牌", "value": "测试", "group": "商品详情"}],
        "good_reviews": [{"content": str(index)} for index in range(6)],
        "bad_reviews": [{"content": str(index)} for index in range(3)],
    }
    _apply_detail_output_contract(detail)
    assert detail["product_url"] == "https://item.jd.com/1.html"
    assert len(detail["good_reviews"]) == 5
    assert len(detail["bad_reviews"]) == 2
    assert detail["good_reviews_status"]["target_count"] == 5
    assert detail["bad_reviews_status"]["target_count"] == 2
