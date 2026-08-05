from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

playwright_browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "").strip()
if playwright_browsers_path:
    browsers_path = Path(playwright_browsers_path)
    if not browsers_path.is_absolute():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PROJECT_ROOT / browsers_path)

from mcp.server.fastmcp import FastMCP

from jd_taobao_mcp.config import Settings
from jd_taobao_mcp.service import ShoppingBrowserService

settings = Settings.from_env()
service = ShoppingBrowserService(settings)

mcp = FastMCP(
    "JD-Taobao-Browser",
    instructions=(
        "用于在用户本机可见浏览器中浏览京东、淘宝和天猫，并提取页面与商品数据。"
        "必须让用户自己完成扫码、密码、验证码和安全验证。"
        "默认只读：不得购买、加入购物车、结算、支付、关注、收藏、删除或修改账户信息。"
        "优先使用 search_products 和 get_product_detail；只有页面结构变化时才使用通用点击工具。"
        "商品详情输出有硬约束：必须包含 product_url、product_parameters、good_reviews、bad_reviews "
        "及对应 status 字段；good_reviews 目标最多 5 条，bad_reviews 目标最多 2 条；"
        "缺失或不足时必须用空数组或不足目标条数和 status.reason 说明原因。"
        "不要高频、大规模采集。元素 ref 在页面变化后会失效，点击或导航后应重新调用 list_page_elements。"
    ),
)


@mcp.tool()
async def browser_start() -> dict[str, Any]:
    """启动一个带独立持久化资料目录的可见 Chromium 浏览器。"""
    return await service.taobao_browser.start()


@mcp.tool()
async def browser_status() -> dict[str, Any]:
    """查看浏览器是否运行、当前页面和资料目录。"""
    return {
        "jd": await service.jd_browser.status(),
        "taobao": await service.taobao_browser.status(),
    }


@mcp.tool()
async def open_login(platform: str) -> dict[str, Any]:
    """打开京东或淘宝登录页，由用户在浏览器窗口中手动登录。

    Args:
        platform: jd 或 taobao。
    """
    platform = platform.strip().lower()
    return await service._browser_for_platform(platform).open_login(platform)


@mcp.tool()
async def check_login(platform: str) -> dict[str, Any]:
    """根据页面与 Cookie 名称判断京东或淘宝是否可能已登录，不返回 Cookie 值。

    Args:
        platform: jd 或 taobao。
    """
    platform = platform.strip().lower()
    return await service._browser_for_platform(platform).check_login(platform)


@mcp.tool()
async def open_url(url: str) -> dict[str, Any]:
    """打开京东、淘宝或天猫 URL。其他域名会被拒绝。"""
    from jd_taobao_mcp.service import platform_from_url

    platform = platform_from_url(url)
    return await service._browser_for_platform(platform).navigate(url)


@mcp.tool()
async def search_products(
    platform: str,
    keyword: str,
    max_results: int = 20,
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = "default",
    include_details: bool = True,
) -> dict[str, Any]:
    """搜索京东或淘宝商品并返回结构化列表；默认逐个补详情硬约束字段。

    Args:
        platform: jd 或 taobao。
        keyword: 商品关键词。
        max_results: 最多返回数量；受环境变量上限约束。
        min_price: 可选最低价格，本地过滤。
        max_price: 可选最高价格，本地过滤。
        sort: default、price_asc 或 price_desc；排序在提取结果上本地完成。
        include_details: 默认 true。逐个打开结果商品页，并强制每个商品返回
            product_url、product_parameters、最多 5 条 good_reviews、最多 2 条 bad_reviews 及对应 status 字段。
    """
    return await service.search_products(
        platform=platform,
        keyword=keyword,
        max_results=max_results,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        include_details=include_details,
    )


@mcp.tool()
async def get_product_detail(url: str) -> dict[str, Any]:
    """打开商品页并提取详情；硬约束返回产品链接、产品参数、最多 5 条好评、最多 2 条差评及 status。"""
    return await service.get_product_detail(url)


@mcp.tool()
async def page_snapshot(max_chars: int | None = None) -> dict[str, Any]:
    """获取当前页面可见文本、链接、表单和基础元数据。"""
    return await service.browser.snapshot(max_chars=max_chars)


@mcp.tool()
async def extract_current_page() -> dict[str, Any]:
    """对当前京东/淘宝/天猫页面同时执行通用快照和商品字段提取。"""
    return await service.extract_current_page()


@mcp.tool()
async def list_page_elements(limit: int = 80) -> dict[str, Any]:
    """列出当前页面可见的链接、按钮、输入框等，并分配短期 ref。"""
    return await service.browser.list_elements(limit=limit)


@mcp.tool()
async def click_page_element(ref: str) -> dict[str, Any]:
    """点击 list_page_elements 返回的 ref。

    默认阻止购买、结算、支付、购物车、收藏、关注、删除、地址变更等动作。
    """
    return await service.browser.click(ref)


@mcp.tool()
async def type_into_element(
    ref: str, text: str, press_enter: bool = False
) -> dict[str, Any]:
    """向当前页面的普通输入框输入文字，可选择按回车。

    密码、验证码、银行卡、身份证和支付认证字段会被拒绝。
    """
    return await service.browser.type_text(ref, text, press_enter=press_enter)


@mcp.tool()
async def scroll_page(direction: str = "down", amount: int = 900) -> dict[str, Any]:
    """向上或向下滚动当前页面。"""
    return await service.browser.scroll(direction=direction, amount=amount)


@mcp.tool()
async def go_back() -> dict[str, Any]:
    """返回浏览器历史中的上一页。"""
    return await service.browser.go_back()


@mcp.tool()
async def take_screenshot(full_page: bool = False) -> dict[str, Any]:
    """将当前页面截图保存到本地 artifacts 目录。"""
    return await service.browser.screenshot(full_page=full_page)


@mcp.tool()
async def browser_close() -> dict[str, Any]:
    """关闭浏览器；持久化登录资料仍保留在本地独立目录。"""
    results = {
        "jd": await service.jd_browser.close(),
        "taobao": await service.taobao_browser.close(),
    }
    return {"success": True, "results": results}


def main() -> None:
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
