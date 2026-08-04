from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus, urlparse

from .browser import BrowserController
from .config import Settings
from .extractors import extract_jd_search, extract_product_detail, extract_taobao_search
from .safety import page_requires_user_verification


class ShoppingBrowserService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.browser = BrowserController(settings)

    async def search_products(
        self,
        platform: str,
        keyword: str,
        max_results: int = 20,
        min_price: float | None = None,
        max_price: float | None = None,
        sort: str = "default",
        include_details: bool = True,
    ) -> dict[str, Any]:
        platform = _validate_platform(platform)
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("keyword 不能为空")
        if len(keyword) > 200:
            raise ValueError("keyword 最多 200 个字符")
        max_results = max(1, min(max_results, self.settings.max_search_results))
        if min_price is not None and min_price < 0:
            raise ValueError("min_price 不能小于 0")
        if max_price is not None and max_price < 0:
            raise ValueError("max_price 不能小于 0")
        if min_price is not None and max_price is not None and min_price > max_price:
            raise ValueError("min_price 不能大于 max_price")
        if sort not in {"default", "price_asc", "price_desc"}:
            raise ValueError("sort 仅支持 default、price_asc、price_desc")

        url = (
            f"https://search.jd.com/Search?keyword={quote_plus(keyword)}"
            if platform == "jd"
            else f"https://s.taobao.com/search?q={quote_plus(keyword)}"
        )
        nav = await self.browser.navigate(url)
        async with self.browser.lock:
            page = await self.browser.get_page()
            # 让懒加载商品出现，但保持低频和小规模。
            await page.mouse.wheel(0, 900)
            await page.wait_for_timeout(self.settings.action_delay_ms)
            body_text = ""
            if await page.locator("body").count():
                body_text = await page.locator("body").inner_text(timeout=5_000)
            if page_requires_user_verification(body_text, page.url):
                return {
                    "success": False,
                    "platform": platform,
                    "keyword": keyword,
                    "requires_user_verification": True,
                    "url": page.url,
                    "message": "页面要求人工验证。请在弹出的浏览器中完成验证，再重新调用搜索。",
                    "items": [],
                    "detail_output_contract": _detail_output_contract(),
                }
            items = (
                await extract_jd_search(page, max_results * 2)
                if platform == "jd"
                else await extract_taobao_search(page, max_results * 2)
            )

        filtered = [
            item
            for item in items
            if _price_matches(item.get("price"), min_price, max_price)
        ]
        if sort == "price_asc":
            filtered.sort(key=lambda item: (item.get("price") is None, item.get("price") or 0))
        elif sort == "price_desc":
            filtered.sort(
                key=lambda item: (item.get("price") is not None, item.get("price") or 0),
                reverse=True,
            )
        filtered = filtered[:max_results]
        if include_details:
            await self._enrich_search_results_with_details(filtered)
        return {
            "success": True,
            "platform": platform,
            "keyword": keyword,
            "search_url": nav.get("url", url),
            "count": len(filtered),
            "filters": {
                "min_price": min_price,
                "max_price": max_price,
                "sort": sort,
                "include_details": include_details,
            },
            "items": filtered,
            "detail_output_contract": _detail_output_contract(),
            "note": (
                "价格和销量来自当前页面可见内容，促销价、地区价和登录态可能导致差异。"
                "默认 include_details=true，会逐个打开商品详情页。每个商品强制返回 "
                "product_parameters、good_reviews、bad_reviews；页面未展示或提取不到时"
                "返回空数组，并在对应 status 字段说明原因。"
            ),
        }

    async def get_product_detail(self, url: str) -> dict[str, Any]:
        platform = platform_from_url(url)
        nav = await self.browser.navigate(url)
        async with self.browser.lock:
            page = await self.browser.get_page()
            body_text = ""
            if await page.locator("body").count():
                body_text = await page.locator("body").inner_text(timeout=5_000)
            if page_requires_user_verification(body_text, page.url):
                return {
                    "success": False,
                    "platform": platform,
                    "url": page.url,
                    "requires_user_verification": True,
                    "message": "商品页要求人工验证。请在浏览器窗口中完成验证后重试。",
                    **_empty_detail_contract_fields("requires_user_verification"),
                }
            await self._prepare_product_detail_page(page)
            detail = await extract_product_detail(page, platform)
        _apply_detail_output_contract(detail)
        detail.update(
            {
                "success": True,
                "requires_user_verification": nav.get(
                    "requires_user_verification", False
                ),
                "note": (
                    "字段由页面 DOM、Meta 和 JSON-LD 综合提取。硬约束字段始终返回："
                    "product_parameters、good_reviews、bad_reviews；不足 5 条或为空时，"
                    "以 status 字段说明页面未展示、评价不足或提取不到。"
                ),
            }
        )
        return detail

    async def extract_current_page(self) -> dict[str, Any]:
        snapshot = await self.browser.snapshot()
        platform = platform_from_url(snapshot["url"])
        async with self.browser.lock:
            page = await self.browser.get_page()
            detail = await extract_product_detail(page, platform)
        _apply_detail_output_contract(detail)
        return {
            "success": True,
            "snapshot": snapshot,
            "product_like_data": detail,
            "detail_output_contract": _detail_output_contract(),
        }

    async def _enrich_search_results_with_details(
        self, items: list[dict[str, Any]]
    ) -> None:
        for item in items:
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            try:
                detail = await self.get_product_detail(url)
            except Exception as exc:
                item["detail_success"] = False
                item["detail_error"] = str(exc)
                item.update(_empty_detail_contract_fields("detail_error"))
                continue

            item["detail_success"] = bool(detail.get("success"))
            if detail.get("requires_user_verification"):
                item["detail_requires_user_verification"] = True
                item["detail_message"] = detail.get("message", "")
                item.update(_empty_detail_contract_fields("requires_user_verification"))
                break

            for key in (
                "product_parameters",
                "high_praise_reviews",
                "high_dissatisfied_reviews",
                "good_reviews",
                "bad_reviews",
                "product_parameters_status",
                "good_reviews_status",
                "bad_reviews_status",
                "detail_output_contract",
            ):
                item[key] = detail.get(key, [] if key.endswith("_reviews") or key == "product_parameters" else {})
            if not item.get("shop"):
                item["shop"] = detail.get("shop", "")
            if item.get("price") is None:
                item["price"] = detail.get("price")
                item["price_text"] = detail.get("price_text", "")

    async def _prepare_product_detail_page(self, page: Any) -> None:
        await page.wait_for_timeout(self.settings.action_delay_ms)
        for _ in range(2):
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(self.settings.action_delay_ms)

        if "jd.com" in page.url or "360buy.com" in page.url:
            review_tab_selectors = (
                "#detail .tab-main li:has-text('商品评价')",
                ".tab-main li:has-text('商品评价')",
                "a:has-text('商品评价')",
                "li:has-text('商品评价')",
            )
        else:
            review_tab_selectors = (
                "a:has-text('累计评价')",
                "button:has-text('累计评价')",
                "a:has-text('宝贝评价')",
                "button:has-text('宝贝评价')",
            )
        for selector in review_tab_selectors:
            locator = page.locator(selector).first
            if not await locator.count():
                continue
            try:
                await locator.click(timeout=2_000)
                await page.wait_for_timeout(self.settings.action_delay_ms)
                break
            except Exception:
                continue


def _validate_platform(platform: str) -> str:
    normalized = platform.strip().lower()
    if normalized not in {"jd", "taobao"}:
        raise ValueError("platform 仅支持 jd 或 taobao")
    return normalized


def platform_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host == "jd.com" or host.endswith(".jd.com") or host.endswith(".360buy.com"):
        return "jd"
    if host == "taobao.com" or host.endswith(".taobao.com") or host == "tmall.com" or host.endswith(".tmall.com"):
        return "taobao"
    raise ValueError("URL 必须属于京东、淘宝或天猫。")


def _price_matches(
    price: float | None, min_price: float | None, max_price: float | None
) -> bool:
    if price is None:
        return min_price is None and max_price is None
    if min_price is not None and price < min_price:
        return False
    if max_price is not None and price > max_price:
        return False
    return True


def _apply_detail_output_contract(detail: dict[str, Any]) -> None:
    product_parameters = _list_value(detail.get("product_parameters"))
    good_reviews = _list_value(
        detail.get("good_reviews") or detail.get("high_praise_reviews")
    )[:5]
    bad_reviews = _list_value(
        detail.get("bad_reviews") or detail.get("high_dissatisfied_reviews")
    )[:5]

    detail["product_parameters"] = product_parameters
    detail["good_reviews"] = good_reviews
    detail["bad_reviews"] = bad_reviews
    detail["high_praise_reviews"] = good_reviews
    detail["high_dissatisfied_reviews"] = bad_reviews
    detail["product_parameters_status"] = _field_status(
        "product_parameters", len(product_parameters)
    )
    detail["good_reviews_status"] = _field_status("good_reviews", len(good_reviews))
    detail["bad_reviews_status"] = _field_status("bad_reviews", len(bad_reviews))
    detail["detail_output_contract"] = _detail_output_contract()


def _empty_detail_contract_fields(reason: str) -> dict[str, Any]:
    return {
        "product_parameters": [],
        "good_reviews": [],
        "bad_reviews": [],
        "high_praise_reviews": [],
        "high_dissatisfied_reviews": [],
        "product_parameters_status": _field_status("product_parameters", 0, reason),
        "good_reviews_status": _field_status("good_reviews", 0, reason),
        "bad_reviews_status": _field_status("bad_reviews", 0, reason),
        "detail_output_contract": _detail_output_contract(),
    }


def _detail_output_contract() -> dict[str, Any]:
    return {
        "required_fields": [
            "product_parameters",
            "good_reviews",
            "bad_reviews",
            "product_parameters_status",
            "good_reviews_status",
            "bad_reviews_status",
        ],
        "review_limit_each": 5,
        "empty_field_policy": (
            "字段必须出现；页面没有展示、评价数量不足、需要人工验证或提取失败时，"
            "返回空数组或不足 5 条，并在对应 status.reason 中说明。"
        ),
    }


def _field_status(field: str, count: int, reason: str | None = None) -> dict[str, Any]:
    if count:
        return {
            "field": field,
            "required": True,
            "count": count,
            "complete": field == "product_parameters" or count >= 5,
            "reason": "ok" if field == "product_parameters" or count >= 5 else "visible_reviews_less_than_5",
        }
    return {
        "field": field,
        "required": True,
        "count": 0,
        "complete": False,
        "reason": reason or "not_visible_or_not_extracted",
    }


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
