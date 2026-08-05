import pytest

from jd_taobao_mcp.safety import (
    ElementSafetyMetadata,
    SafetyError,
    ensure_allowed_url,
    ensure_click_allowed,
    ensure_typing_allowed,
    is_allowed_url,
    page_requires_user_verification,
)


def test_allowed_domains():
    assert is_allowed_url("https://item.jd.com/123.html")
    assert is_allowed_url("https://s.taobao.com/search?q=phone")
    assert is_allowed_url("https://detail.tmall.com/item.htm?id=1")
    assert not is_allowed_url("https://example.com")
    assert not is_allowed_url("file:///etc/passwd")


def test_disallowed_url_raises():
    with pytest.raises(SafetyError):
        ensure_allowed_url("https://example.com")


def test_transaction_click_blocked():
    with pytest.raises(SafetyError):
        ensure_click_allowed(
            ElementSafetyMetadata(text="立即购买"),
            allow_state_changing_actions=False,
        )


def test_read_only_click_allowed():
    ensure_click_allowed(
        ElementSafetyMetadata(text="商品参数"),
        allow_state_changing_actions=False,
    )


def test_sensitive_typing_blocked():
    with pytest.raises(SafetyError):
        ensure_typing_allowed(ElementSafetyMetadata(input_type="password"))
    with pytest.raises(SafetyError):
        ensure_typing_allowed(ElementSafetyMetadata(placeholder="请输入短信验证码"))


def test_verification_detection():
    assert page_requires_user_verification("请拖动滑块完成安全验证")
    assert not page_requires_user_verification("普通商品详情页面")
    assert not page_requires_user_verification("LOOIROBOT AI 手机机器人商品详情")
