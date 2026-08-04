from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from .helpers import compact_text, dedupe_dicts, normalize_url, parse_price


async def extract_jd_search(page: Page, max_results: int) -> list[dict[str, Any]]:
    raw = await page.evaluate(
        """
        (limit) => {
          const cards = [...document.querySelectorAll('#J_goodsList .gl-item, li.gl-item')].slice(0, limit);
          return cards.map((card) => {
            const link = card.querySelector('.p-name a, a[href*="item.jd.com"]');
            const title = card.querySelector('.p-name em, .p-name')?.innerText || link?.innerText || '';
            const price = card.querySelector('.p-price i, .p-price, [class*="price"]')?.innerText || '';
            const shop = card.querySelector('.p-shop a, .p-shop, [class*="shop"]')?.innerText || '';
            const comment = card.querySelector('.p-commit a, .p-commit')?.innerText || '';
            const image = card.querySelector('img');
            return {
              title,
              price_text: price,
              shop,
              comment_text: comment,
              url: link?.href || '',
              image: image?.getAttribute('data-lazy-img') || image?.getAttribute('data-img') || image?.src || ''
            };
          });
        }
        """,
        max_results,
    )
    items: list[dict[str, Any]] = []
    for item in raw:
        title = compact_text(item.get("title"), 300)
        url = normalize_url(page.url, item.get("url"))
        if not title or not url:
            continue
        items.append(
            {
                "platform": "jd",
                "title": title,
                "price": parse_price(item.get("price_text")),
                "price_text": compact_text(item.get("price_text"), 80),
                "shop": compact_text(item.get("shop"), 120),
                "comment_text": compact_text(item.get("comment_text"), 80),
                "url": url,
                "image": normalize_url(page.url, item.get("image")),
            }
        )
    if items:
        return dedupe_dicts(items, "url")[:max_results]
    return await _fallback_product_links(page, "jd", max_results)


async def extract_taobao_search(page: Page, max_results: int) -> list[dict[str, Any]]:
    raw = await page.evaluate(
        r"""
        (limit) => {
          const links = [...document.querySelectorAll('a[href]')]
            .filter((a) => /item\.taobao\.com\/item\.htm|detail\.tmall\.com\/item\.htm/.test(a.href));
          const seen = new Set();
          const out = [];
          for (const link of links) {
            if (seen.has(link.href)) continue;
            seen.add(link.href);
            const card = link.closest('[data-spm], [class*="Card"], [class*="card"], [class*="item"], li, article') || link.parentElement;
            const text = (card?.innerText || link.innerText || '').trim();
            if (!text) continue;
            const image = card?.querySelector('img') || link.querySelector('img');
            out.push({
              url: link.href,
              title: link.getAttribute('title') || link.innerText || image?.getAttribute('alt') || text.split('\n')[0] || '',
              card_text: text,
              image: image?.getAttribute('data-src') || image?.getAttribute('data-ks-lazyload') || image?.src || ''
            });
            if (out.length >= limit) break;
          }
          return out;
        }
        """,
        max_results * 3,
    )
    items: list[dict[str, Any]] = []
    for item in raw:
        card_text = compact_text(item.get("card_text"), 600)
        title = compact_text(item.get("title"), 300)
        if not title or len(title) < 2:
            title = compact_text(card_text.split(" ¥")[0], 300)
        url = normalize_url(page.url, item.get("url"))
        if not title or not url:
            continue
        items.append(
            {
                "platform": "taobao",
                "title": title,
                "price": parse_price(card_text),
                "price_text": _first_price_text(card_text),
                "shop": "",
                "comment_text": "",
                "url": url,
                "image": normalize_url(page.url, item.get("image")),
                "card_text": card_text,
            }
        )
    if items:
        return dedupe_dicts(items, "url")[:max_results]
    return await _fallback_product_links(page, "taobao", max_results)


def _first_price_text(text: str) -> str:
    if not text:
        return ""
    for token in text.split(" "):
        if "¥" in token or "￥" in token:
            return token[:80]
    return ""


async def _fallback_product_links(
    page: Page, platform: str, max_results: int
) -> list[dict[str, Any]]:
    pattern = "item.jd.com" if platform == "jd" else "item.taobao.com|detail.tmall.com"
    raw = await page.evaluate(
        """
        ({pattern, limit}) => {
          const re = new RegExp(pattern);
          const out = [];
          const seen = new Set();
          for (const a of document.querySelectorAll('a[href]')) {
            if (!re.test(a.href) || seen.has(a.href)) continue;
            const text = (a.innerText || a.getAttribute('title') || a.querySelector('img')?.alt || '').trim();
            if (!text) continue;
            seen.add(a.href);
            const parentText = (a.closest('li,article,div')?.innerText || text).trim();
            out.push({url: a.href, title: text, card_text: parentText});
            if (out.length >= limit) break;
          }
          return out;
        }
        """,
        {"pattern": pattern, "limit": max_results},
    )
    return [
        {
            "platform": platform,
            "title": compact_text(item.get("title"), 300),
            "price": parse_price(item.get("card_text")),
            "price_text": "",
            "shop": "",
            "comment_text": "",
            "url": normalize_url(page.url, item.get("url")),
            "image": None,
            "card_text": compact_text(item.get("card_text"), 600),
        }
        for item in raw
        if item.get("url") and item.get("title")
    ]
