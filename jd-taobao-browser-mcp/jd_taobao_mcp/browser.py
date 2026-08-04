from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from playwright.async_api import (
    BrowserContext,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from .config import Settings
from .safety import (
    ElementSafetyMetadata,
    SafetyError,
    ensure_allowed_url,
    ensure_click_allowed,
    ensure_typing_allowed,
    page_requires_user_verification,
)


class BrowserController:
    """Single persistent Playwright browser controlled through serialized MCP tools."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._lock = asyncio.Lock()

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    async def start(self) -> dict[str, Any]:
        async with self._lock:
            await self._start_unlocked()
            page = await self._active_page_unlocked()
            return {
                "success": True,
                "message": "浏览器已启动。首次使用请调用 open_login，并在弹出的浏览器中手动扫码或登录。",
                "headless": self.settings.headless,
                "profile_dir": str(self.settings.profile_dir),
                "current_url": page.url,
            }

    async def _start_unlocked(self) -> None:
        if self._context is not None:
            return
        self.settings.profile_dir.mkdir(parents=True, exist_ok=True)
        self.settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        launch_options: dict[str, Any] = {
            "headless": self.settings.headless,
            "slow_mo": self.settings.slow_mo_ms,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "accept_downloads": False,
            "viewport": {"width": 1440, "height": 1000},
        }
        if self.settings.browser_channel:
            launch_options["channel"] = self.settings.browser_channel
        if self.settings.proxy:
            launch_options["proxy"] = {"server": self.settings.proxy}
        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                str(self.settings.profile_dir), **launch_options
            )
        except Exception:
            if self.settings.browser_channel:
                launch_options.pop("channel", None)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    str(self.settings.profile_dir), **launch_options
                )
            else:
                raise
        self._context.set_default_navigation_timeout(
            self.settings.navigation_timeout_ms
        )
        self._context.set_default_timeout(self.settings.action_timeout_ms)
        pages = self._context.pages
        self._page = pages[-1] if pages else await self._context.new_page()

    async def _active_page_unlocked(self) -> Page:
        await self._start_unlocked()
        assert self._context is not None
        if self._page is None or self._page.is_closed():
            pages = [page for page in self._context.pages if not page.is_closed()]
            self._page = pages[-1] if pages else await self._context.new_page()
        return self._page

    async def status(self) -> dict[str, Any]:
        async with self._lock:
            running = self._context is not None
            if not running:
                return {"running": False, "message": "浏览器尚未启动。"}
            page = await self._active_page_unlocked()
            return {
                "running": True,
                "current_url": page.url,
                "title": await page.title(),
                "pages": len([p for p in self._context.pages if not p.is_closed()]),
                "profile_dir": str(self.settings.profile_dir),
            }

    async def navigate(self, url: str) -> dict[str, Any]:
        ensure_allowed_url(url)
        async with self._lock:
            page = await self._active_page_unlocked()
            try:
                response = await page.goto(url, wait_until="domcontentloaded")
            except PlaywrightTimeoutError:
                response = None
            await self._settle(page)
            ensure_allowed_url(page.url)
            return await self._navigation_result(page, response.status if response else None)

    async def _navigation_result(self, page: Page, status: int | None) -> dict[str, Any]:
        text = await page.locator("body").inner_text(timeout=5_000) if await page.locator("body").count() else ""
        return {
            "success": True,
            "url": page.url,
            "title": await page.title(),
            "http_status": status,
            "requires_user_verification": page_requires_user_verification(text, page.url),
            "message": (
                "页面要求人工验证，请直接在浏览器窗口中完成后再继续。"
                if page_requires_user_verification(text, page.url)
                else "页面已打开。"
            ),
        }

    async def open_login(self, platform: str) -> dict[str, Any]:
        url = {
            "jd": "https://passport.jd.com/new/login.aspx",
            "taobao": "https://login.taobao.com/member/login.jhtml",
        }.get(platform)
        if not url:
            raise ValueError("platform 仅支持 jd 或 taobao")
        result = await self.navigate(url)
        result["message"] = (
            "登录页已打开。请在浏览器窗口中手动扫码、输入验证码或完成其他验证；"
            "不要把密码或验证码交给 MCP。登录完成后调用 check_login。"
        )
        return result

    async def check_login(self, platform: str) -> dict[str, Any]:
        home = {
            "jd": "https://www.jd.com/",
            "taobao": "https://www.taobao.com/",
        }.get(platform)
        if not home:
            raise ValueError("platform 仅支持 jd 或 taobao")
        async with self._lock:
            page = await self._active_page_unlocked()
            if not page.url or platform not in page.url:
                try:
                    await page.goto(home, wait_until="domcontentloaded")
                except PlaywrightTimeoutError:
                    pass
                await self._settle(page)
            body_text = ""
            if await page.locator("body").count():
                body_text = await page.locator("body").inner_text(timeout=5_000)
            cookies = await self._context.cookies() if self._context else []
            domain_token = "jd.com" if platform == "jd" else "taobao.com"
            relevant_cookie_names = sorted(
                {
                    cookie["name"]
                    for cookie in cookies
                    if domain_token in cookie.get("domain", "")
                }
            )
            likely_logged_in = self._login_heuristic(platform, body_text, relevant_cookie_names)
            return {
                "platform": platform,
                "likely_logged_in": likely_logged_in,
                "current_url": page.url,
                "relevant_cookie_count": len(relevant_cookie_names),
                "cookie_names": relevant_cookie_names[:30],
                "requires_user_verification": page_requires_user_verification(body_text, page.url),
                "message": (
                    "检测到较强的登录迹象。"
                    if likely_logged_in
                    else "未能确认已登录；请查看浏览器窗口并手动完成登录。"
                ),
            }

    @staticmethod
    def _login_heuristic(platform: str, body_text: str, cookie_names: list[str]) -> bool:
        text = body_text[:10_000]
        if platform == "jd":
            cookie_hit = any(name in cookie_names for name in {"pt_key", "pin", "thor"})
            page_hit = "请登录" not in text and any(token in text for token in ("我的京东", "退出", "你好"))
            return cookie_hit or page_hit
        cookie_hit = any(name in cookie_names for name in {"tracknick", "lgc", "_tb_token_"})
        page_hit = "亲，请登录" not in text and any(token in text for token in ("我的淘宝", "退出", "消息"))
        return cookie_hit or page_hit

    async def snapshot(self, max_chars: int | None = None) -> dict[str, Any]:
        async with self._lock:
            page = await self._active_page_unlocked()
            max_chars = max_chars or self.settings.max_page_text_chars
            data = await page.evaluate(
                r"""
                (maxChars) => {
                  const links = [...document.querySelectorAll('a[href]')]
                    .filter(a => {
                      const r = a.getBoundingClientRect();
                      return r.width > 0 && r.height > 0;
                    })
                    .slice(0, 120)
                    .map(a => ({text: (a.innerText || a.title || '').trim().slice(0, 200), href: a.href}));
                  const forms = [...document.querySelectorAll('form')].slice(0, 20).map(form => ({
                    action: form.action,
                    method: form.method,
                    text: (form.innerText || '').trim().slice(0, 500)
                  }));
                  const bodyText = (document.body?.innerText || '').replace(/\n{3,}/g, '\n\n');
                  return {
                    url: location.href,
                    title: document.title,
                    text: bodyText.slice(0, maxChars),
                    links,
                    forms,
                    meta_description: document.querySelector('meta[name="description"]')?.content || ''
                  };
                }
                """,
                max_chars,
            )
            data["requires_user_verification"] = page_requires_user_verification(
                data.get("text", ""), page.url
            )
            return data

    async def list_elements(self, limit: int = 80) -> dict[str, Any]:
        limit = max(1, min(limit, 200))
        async with self._lock:
            page = await self._active_page_unlocked()
            elements = await page.evaluate(
                r"""
                (limit) => {
                  for (const el of document.querySelectorAll('[data-mcp-ref]')) el.removeAttribute('data-mcp-ref');
                  const candidates = [...document.querySelectorAll(
                    'a[href],button,input,textarea,select,[role="button"],[onclick],[tabindex]:not([tabindex="-1"])'
                  )];
                  const out = [];
                  let index = 1;
                  for (const el of candidates) {
                    const style = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    if (style.visibility === 'hidden' || style.display === 'none' || r.width < 2 || r.height < 2) continue;
                    const ref = `e${index++}`;
                    el.setAttribute('data-mcp-ref', ref);
                    out.push({
                      ref,
                      tag: el.tagName.toLowerCase(),
                      text: (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 240),
                      role: el.getAttribute('role') || '',
                      aria_label: el.getAttribute('aria-label') || '',
                      title: el.getAttribute('title') || '',
                      placeholder: el.getAttribute('placeholder') || '',
                      type: el.getAttribute('type') || '',
                      name: el.getAttribute('name') || '',
                      href: el.href || '',
                      disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
                      bbox: {x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height)}
                    });
                    if (out.length >= limit) break;
                  }
                  return out;
                }
                """,
                limit,
            )
            return {
                "url": page.url,
                "title": await page.title(),
                "count": len(elements),
                "elements": elements,
                "note": "ref 只对当前页面状态有效；页面刷新或点击后请重新调用 list_page_elements。",
            }

    async def click(self, ref: str) -> dict[str, Any]:
        async with self._lock:
            page = await self._active_page_unlocked()
            locator = page.locator(f'[data-mcp-ref="{_escape_css_value(ref)}"]')
            if await locator.count() != 1:
                raise ValueError("未找到唯一元素。请重新调用 list_page_elements 获取最新 ref。")
            metadata = await self._element_metadata(locator)
            body_text = ""
            if await page.locator("body").count():
                body_text = await page.locator("body").inner_text(timeout=5_000)
            if page_requires_user_verification(body_text, page.url):
                raise SafetyError(
                    "当前页面包含验证码或安全验证，请在浏览器窗口中手动处理，MCP 不操作验证控件。"
                )
            ensure_click_allowed(
                metadata,
                allow_state_changing_actions=self.settings.allow_state_changing_actions,
            )
            if metadata.href and metadata.href.lower().startswith(("http://", "https://")):
                ensure_allowed_url(metadata.href)
            original_page = page
            before_pages = set(self._context.pages if self._context else [])
            await locator.scroll_into_view_if_needed()
            await locator.click()
            await self._settle(page)
            if self._context:
                new_pages = [p for p in self._context.pages if p not in before_pages and not p.is_closed()]
                if new_pages:
                    self._page = new_pages[-1]
                    page = self._page
                    await self._settle(page)
            try:
                ensure_allowed_url(page.url)
            except SafetyError:
                if page is not original_page:
                    await page.close()
                    self._page = original_page
                else:
                    try:
                        await page.go_back(wait_until="domcontentloaded")
                    except Exception:
                        pass
                raise
            return {
                "success": True,
                "clicked_ref": ref,
                "url": page.url,
                "title": await page.title(),
                "message": "点击完成。页面状态已变化，请重新获取元素列表。",
            }

    async def type_text(self, ref: str, text: str, press_enter: bool = False) -> dict[str, Any]:
        if len(text) > 2_000:
            raise ValueError("单次输入最多 2000 个字符。")
        async with self._lock:
            page = await self._active_page_unlocked()
            locator = page.locator(f'[data-mcp-ref="{_escape_css_value(ref)}"]')
            if await locator.count() != 1:
                raise ValueError("未找到唯一元素。请重新调用 list_page_elements 获取最新 ref。")
            metadata = await self._element_metadata(locator)
            body_text = ""
            if await page.locator("body").count():
                body_text = await page.locator("body").inner_text(timeout=5_000)
            if page_requires_user_verification(body_text, page.url):
                raise SafetyError(
                    "当前页面包含验证码或安全验证，请在浏览器窗口中手动处理，MCP 不向验证页面输入内容。"
                )
            ensure_typing_allowed(metadata)
            original_url = page.url
            await locator.scroll_into_view_if_needed()
            await locator.fill(text)
            if press_enter:
                await locator.press("Enter")
                await self._settle(page)
                try:
                    ensure_allowed_url(page.url)
                except SafetyError:
                    try:
                        await page.goto(original_url, wait_until="domcontentloaded")
                    except Exception:
                        pass
                    raise
            return {
                "success": True,
                "ref": ref,
                "characters_typed": len(text),
                "pressed_enter": press_enter,
                "url": page.url,
                "message": "输入完成。" + (" 已按回车。" if press_enter else ""),
            }

    async def scroll(self, direction: str = "down", amount: int = 900) -> dict[str, Any]:
        if direction not in {"up", "down"}:
            raise ValueError("direction 仅支持 up 或 down")
        amount = max(100, min(amount, 5_000))
        delta = amount if direction == "down" else -amount
        async with self._lock:
            page = await self._active_page_unlocked()
            await page.mouse.wheel(0, delta)
            await self._settle(page, short=True)
            position = await page.evaluate(
                "({x: Math.round(window.scrollX), y: Math.round(window.scrollY), height: document.documentElement.scrollHeight})"
            )
            return {"success": True, "direction": direction, "amount": amount, **position}

    async def go_back(self) -> dict[str, Any]:
        async with self._lock:
            page = await self._active_page_unlocked()
            try:
                await page.go_back(wait_until="domcontentloaded")
            except PlaywrightTimeoutError:
                pass
            await self._settle(page)
            ensure_allowed_url(page.url)
            return {"success": True, "url": page.url, "title": await page.title()}

    async def screenshot(self, full_page: bool = False) -> dict[str, Any]:
        async with self._lock:
            page = await self._active_page_unlocked()
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            path = self.settings.artifacts_dir / f"screenshot-{timestamp}.png"
            await page.screenshot(path=str(path), full_page=full_page)
            return {
                "success": True,
                "path": str(path),
                "url": page.url,
                "full_page": full_page,
                "message": "截图已保存到本地文件。",
            }

    async def get_page(self) -> Page:
        # Callers must hold self.lock while using the returned Page.
        return await self._active_page_unlocked()

    async def close(self) -> dict[str, Any]:
        async with self._lock:
            if self._context is not None:
                await self._context.close()
            if self._playwright is not None:
                await self._playwright.stop()
            self._context = None
            self._playwright = None
            self._page = None
            return {"success": True, "message": "浏览器已关闭，登录状态仍保存在独立资料目录中。"}

    async def _element_metadata(self, locator: Locator) -> ElementSafetyMetadata:
        data = await locator.evaluate(
            """
            (el) => ({
              text: (el.innerText || '').trim(),
              aria_label: el.getAttribute('aria-label') || '',
              title: el.getAttribute('title') || '',
              value: el.value || '',
              href: el.href || '',
              input_type: el.getAttribute('type') || '',
              placeholder: el.getAttribute('placeholder') || '',
              name: el.getAttribute('name') || ''
            })
            """
        )
        return ElementSafetyMetadata(**data)

    async def _settle(self, page: Page, short: bool = False) -> None:
        delay = min(self.settings.action_delay_ms, 300 if short else self.settings.action_delay_ms)
        if delay:
            await page.wait_for_timeout(delay)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except PlaywrightTimeoutError:
            pass


def _escape_css_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
