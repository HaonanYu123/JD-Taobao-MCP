from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, urlparse

from .browser import BrowserController
from .config import Settings
from .extractors import extract_jd_search, extract_product_detail, extract_taobao_search
from .safety import page_requires_user_verification


class ShoppingBrowserService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jd_browser = BrowserController(self._settings_for_platform("jd"))
        self.taobao_browser = BrowserController(self._settings_for_platform("taobao"))
        self.browser = self.taobao_browser

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
            raise ValueError("keyword cannot be empty")
        if len(keyword) > 200:
            raise ValueError("keyword is too long")
        max_results = max(1, min(max_results, self.settings.max_search_results))
        if min_price is not None and min_price < 0:
            raise ValueError("min_price cannot be negative")
        if max_price is not None and max_price < 0:
            raise ValueError("max_price cannot be negative")
        if min_price is not None and max_price is not None and min_price > max_price:
            raise ValueError("min_price cannot be greater than max_price")
        if sort not in {"default", "price_asc", "price_desc"}:
            raise ValueError("sort must be default, price_asc, or price_desc")

        browser = self._browser_for_platform(platform)
        nav = await self._open_search_page(browser, platform, keyword)
        async with browser.lock:
            page = await browser.get_page()
            scroll_rounds = 3 if platform == "taobao" and self.settings.taobao_search_mode == "mobile" else 1
            for _ in range(scroll_rounds):
                await page.mouse.wheel(0, 900)
                await page.wait_for_timeout(self.settings.action_delay_ms)
            body_text = ""
            if await page.locator("body").count():
                body_text = await page.locator("body").inner_text(timeout=5_000)
            items = (
                await extract_jd_search(page, max_results * 2)
                if platform == "jd"
                else await extract_taobao_search(page, max_results * 2)
            )
            requires_verification = page_requires_user_verification(body_text, page.url)
            if requires_verification and not items:
                return {
                    "success": False,
                    "platform": platform,
                    "keyword": keyword,
                    "requires_user_verification": True,
                    "url": page.url,
                    "message": "Page requires manual verification in the visible browser.",
                    "items": [],
                    "detail_output_contract": _detail_output_contract(),
                }

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
            await self._enrich_search_results_with_details(platform, filtered)

        return {
            "success": True,
            "platform": platform,
            "keyword": keyword,
            "search_url": nav.get("url", ""),
            "count": len(filtered),
            "filters": {
                "min_price": min_price,
                "max_price": max_price,
                "sort": sort,
                "include_details": include_details,
            },
            "items": filtered,
            "detail_output_contract": _detail_output_contract(),
            "verification_warning": requires_verification,
            "note": (
                "JD and Taobao use separate browser profiles. Taobao defaults to Chrome "
                "and mobile search; detail extraction looks for Taobao parameter blocks."
            ),
        }

    async def get_product_detail(self, url: str) -> dict[str, Any]:
        platform = platform_from_url(url)
        browser = self._browser_for_platform(platform)
        nav = await browser.navigate(url)
        async with browser.lock:
            page = await browser.get_page()
            body_text = ""
            if await page.locator("body").count():
                body_text = await page.locator("body").inner_text(timeout=5_000)
            requires_verification = page_requires_user_verification(body_text, page.url)
            if requires_verification and not _page_has_product_content(body_text):
                return {
                    "success": False,
                    "platform": platform,
                    "url": page.url,
                    "product_url": page.url,
                    "requires_user_verification": True,
                    "message": "Product page requires manual verification in the visible browser.",
                    **_empty_detail_contract_fields(
                        "requires_user_verification", product_url=page.url
                    ),
                }
            await self._prepare_product_detail_page(page, platform)
            detail = await extract_product_detail(page, platform)
        _apply_detail_output_contract(detail)
        detail.update(
            {
                "success": True,
                "requires_user_verification": False,
                "verification_warning": requires_verification
                or nav.get("requires_user_verification", False),
                "note": (
                    "Fields are extracted from visible DOM, metadata, JSON-LD, and "
                    "platform-specific parameter areas. Missing fields include status reasons."
                ),
            }
        )
        return detail

    async def extract_current_page(self) -> dict[str, Any]:
        snapshot = await self.browser.snapshot()
        platform = platform_from_url(snapshot["url"])
        browser = self._browser_for_platform(platform)
        async with browser.lock:
            page = await browser.get_page()
            detail = await extract_product_detail(page, platform)
        _apply_detail_output_contract(detail)
        return {
            "success": True,
            "snapshot": snapshot,
            "product_like_data": detail,
            "detail_output_contract": _detail_output_contract(),
        }

    async def _enrich_search_results_with_details(
        self, platform: str, items: list[dict[str, Any]]
    ) -> bool:
        for item in items:
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            try:
                detail = await self.get_product_detail(url)
            except Exception as exc:
                item["detail_success"] = False
                item["detail_error"] = str(exc)
                item.update(
                    _empty_detail_contract_fields(
                        "detail_error", product_url=str(url)
                    )
                )
                continue

            item["detail_success"] = bool(detail.get("success"))
            if detail.get("requires_user_verification"):
                item["detail_requires_user_verification"] = True
                item["detail_message"] = detail.get("message", "")
                item.update(
                    _empty_detail_contract_fields(
                        "requires_user_verification", product_url=str(url)
                    )
                )
                continue

            for key in (
                "product_url",
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
                item[key] = detail.get(
                    key,
                    [] if key.endswith("_reviews") or key == "product_parameters" else {},
                )
            if not item.get("shop"):
                item["shop"] = detail.get("shop", "")
            if item.get("price") is None:
                item["price"] = detail.get("price")
                item["price_text"] = detail.get("price_text", "")

    async def _prepare_product_detail_page(self, page: Any, platform: str) -> None:
        await page.wait_for_timeout(self.settings.action_delay_ms)
        for _ in range(2):
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(self.settings.action_delay_ms)

        if platform == "jd":
            await self._prepare_jd_detail_page(page)
        else:
            await self._prepare_taobao_detail_page(page)

    async def _prepare_jd_detail_page(self, page: Any) -> None:
        await self._click_first_available(
            page,
            (
                "#detail .tab-main li:has-text('商品详情')",
                ".tab-main li:has-text('商品详情')",
                "a:has-text('商品详情')",
                "li:has-text('商品详情')",
                "#detail .tab-main li:has-text('规格参数')",
                ".tab-main li:has-text('规格参数')",
            ),
            scroll_after=True,
        )
        await self._click_first_available(
            page,
            (
                "#detail .tab-main li:has-text('商品评价')",
                ".tab-main li:has-text('商品评价')",
                "a:has-text('商品评价')",
                "li:has-text('商品评价')",
            ),
        )

    async def _prepare_taobao_detail_page(self, page: Any) -> None:
        await self._click_first_available(
            page,
            (
                "text=/^(参数|商品参数|宝贝参数|规格参数)$/",
                "button:has-text('参数')",
                "a:has-text('参数')",
                "[class*='parameter' i]",
                "[class*='params' i]",
            ),
        )
        await self._click_first_available(
            page,
            (
                "text=/^(评价|宝贝评价|累计评价)$/",
                "button:has-text('评价')",
                "a:has-text('评价')",
            ),
        )

    async def _click_first_available(
        self, page: Any, selectors: tuple[str, ...], *, scroll_after: bool = False
    ) -> None:
        for selector in selectors:
            locator = page.locator(selector).first
            if not await locator.count():
                continue
            try:
                await locator.click(timeout=2_000)
                await page.wait_for_timeout(self.settings.action_delay_ms)
                if scroll_after:
                    await page.mouse.wheel(0, 500)
                    await page.wait_for_timeout(self.settings.action_delay_ms)
                return True
            except Exception:
                continue
        return False

    def _settings_for_platform(self, platform: str) -> Settings:
        if platform == "taobao":
            executable_path = (
                self.settings.taobao_browser_executable_path
                or _default_chrome_path()
                or self.settings.browser_executable_path
            )
            return replace(
                self.settings,
                browser_channel=None if executable_path else self.settings.browser_channel,
                browser_executable_path=executable_path,
                profile_dir=self.settings.profile_dir / "taobao",
            )
        executable_path = (
            self.settings.jd_browser_executable_path
            or self.settings.browser_executable_path
        )
        return replace(
            self.settings,
            browser_executable_path=executable_path,
            profile_dir=self.settings.profile_dir / "jd",
        )

    def _browser_for_platform(self, platform: str) -> BrowserController:
        platform = _validate_platform(platform)
        self.browser = self.taobao_browser if platform == "taobao" else self.jd_browser
        return self.browser

    async def _open_search_page(
        self, browser: BrowserController, platform: str, keyword: str
    ) -> dict[str, Any]:
        if platform == "jd":
            return await browser.navigate(
                f"https://search.jd.com/Search?keyword={quote_plus(keyword)}"
            )
        if self.settings.taobao_search_mode == "mobile":
            return await browser.navigate(
                f"https://s.m.taobao.com/h5?q={quote(keyword)}"
            )

        nav = await browser.navigate("https://www.taobao.com/")
        async with browser.lock:
            page = await browser.get_page()
            search_box = None
            for selector in (
                'input[name="q"]',
                'input[aria-label*="搜索"]',
                'input[placeholder*="搜索"]',
                "#q",
            ):
                locator = page.locator(selector).first
                if await locator.count():
                    search_box = locator
                    break
            if search_box is None:
                return nav
            await search_box.fill(keyword)
            clicked = await self._click_first_available(
                page,
                (
                    'button:has-text("搜索")',
                    'input[type="submit"]',
                    '[role="button"]:has-text("搜索")',
                ),
            )
            if not clicked:
                await search_box.press("Enter")
            await page.wait_for_timeout(self.settings.action_delay_ms)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5_000)
            except Exception:
                pass
            if "s.taobao.com/search" not in page.url:
                fallback_url = f"https://s.taobao.com/search?q={quote(keyword)}"
                try:
                    response = await page.goto(fallback_url, wait_until="domcontentloaded")
                    await page.wait_for_timeout(self.settings.action_delay_ms)
                    nav = {**nav, "http_status": response.status if response else None}
                except Exception:
                    pass
            return {**nav, "url": page.url}


def _validate_platform(platform: str) -> str:
    normalized = platform.strip().lower()
    if normalized not in {"jd", "taobao"}:
        raise ValueError("platform must be jd or taobao")
    return normalized


def platform_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host == "jd.com" or host.endswith(".jd.com") or host.endswith(".360buy.com"):
        return "jd"
    if (
        host == "taobao.com"
        or host.endswith(".taobao.com")
        or host == "tmall.com"
        or host.endswith(".tmall.com")
    ):
        return "taobao"
    raise ValueError("URL must belong to JD, Taobao, or Tmall")


def _default_chrome_path() -> Path | None:
    candidates = (
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    )
    return next((path for path in candidates if path.exists()), None)


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
    product_url = detail.get("product_url") or detail.get("url") or ""
    product_parameters = _list_value(detail.get("product_parameters"))
    good_reviews = _list_value(
        detail.get("good_reviews") or detail.get("high_praise_reviews")
    )[:5]
    bad_reviews = _list_value(
        detail.get("bad_reviews") or detail.get("high_dissatisfied_reviews")
    )[:2]

    detail["product_url"] = product_url
    detail["product_parameters"] = product_parameters
    detail["good_reviews"] = good_reviews
    detail["bad_reviews"] = bad_reviews
    detail["high_praise_reviews"] = good_reviews
    detail["high_dissatisfied_reviews"] = bad_reviews
    detail["product_parameters_status"] = _field_status(
        "product_parameters", len(product_parameters)
    )
    detail["good_reviews_status"] = _field_status(
        "good_reviews", len(good_reviews), target_count=5
    )
    detail["bad_reviews_status"] = _field_status(
        "bad_reviews", len(bad_reviews), target_count=2
    )
    detail["detail_output_contract"] = _detail_output_contract()


def _empty_detail_contract_fields(reason: str, *, product_url: str = "") -> dict[str, Any]:
    return {
        "product_url": product_url,
        "product_parameters": [],
        "good_reviews": [],
        "bad_reviews": [],
        "high_praise_reviews": [],
        "high_dissatisfied_reviews": [],
        "product_parameters_status": _field_status("product_parameters", 0, reason),
        "good_reviews_status": _field_status(
            "good_reviews", 0, reason, target_count=5
        ),
        "bad_reviews_status": _field_status(
            "bad_reviews", 0, reason, target_count=2
        ),
        "detail_output_contract": _detail_output_contract(),
    }


def _detail_output_contract() -> dict[str, Any]:
    return {
        "required_fields": [
            "product_url",
            "product_parameters",
            "good_reviews",
            "bad_reviews",
            "product_parameters_status",
            "good_reviews_status",
            "bad_reviews_status",
        ],
        "review_limits": {"good_reviews": 5, "bad_reviews": 2},
        "empty_field_policy": (
            "Required fields are always present. Missing or partial fields include "
            "a status.reason explaining verification, visibility, or extraction limits."
        ),
    }


def _field_status(
    field: str, count: int, reason: str | None = None, *, target_count: int = 1
) -> dict[str, Any]:
    if count:
        complete = field == "product_parameters" or count >= target_count
        return {
            "field": field,
            "required": True,
            "count": count,
            "target_count": target_count,
            "complete": complete,
            "reason": "ok" if complete else f"visible_reviews_less_than_{target_count}",
        }
    return {
        "field": field,
        "required": True,
        "count": 0,
        "target_count": target_count,
        "complete": False,
        "reason": reason or "not_visible_or_not_extracted",
    }


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _page_has_product_content(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "商品详情",
            "买家评价",
            "累计评价",
            "商品编号",
            "参数",
        )
    )
