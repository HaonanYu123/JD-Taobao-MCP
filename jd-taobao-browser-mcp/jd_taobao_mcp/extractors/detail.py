from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Page

from .helpers import compact_text, normalize_url, parse_price


async def extract_product_detail(page: Page, platform: str) -> dict[str, Any]:
    selectors = _selectors(platform)
    raw = await page.evaluate(
        r"""
        (selectors) => {
          const clean = (value, max = 500) => {
            const text = String(value || '').replace(/\s+/g, ' ').trim();
            return max && text.length > max ? text.slice(0, max - 1) + '…' : text;
          };
          const firstText = (items) => {
            for (const selector of items) {
              const el = document.querySelector(selector);
              const text = el?.innerText?.trim() || el?.getAttribute?.('content')?.trim();
              if (text) return text;
            }
            return '';
          };
          const jsonLd = [];
          for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
            try { jsonLd.push(JSON.parse(node.textContent || 'null')); } catch (_) {}
          }
          const specs = [];
          for (const selector of selectors.specs) {
            for (const el of document.querySelectorAll(selector)) {
              const text = (el.innerText || '').trim();
              if (text && text.length < 500) specs.push(text);
              if (specs.length >= 80) break;
            }
            if (specs.length >= 80) break;
          }
          const productParameters = [];
          const parameterSeen = new Set();
          const addParameter = (name, value, group = '') => {
            name = clean(name, 120).replace(/[：:]\s*$/, '');
            value = clean(value, 500);
            group = clean(group, 120);
            if (!name || !value || name === value) return;
            const key = `${group}\u0000${name}\u0000${value}`;
            if (parameterSeen.has(key)) return;
            parameterSeen.add(key);
            productParameters.push({name, value, group});
          };
          const splitParameterText = (text) => {
            text = clean(text, 600);
            const index = text.search(/[：:]/);
            if (index <= 0 || index >= text.length - 1) return null;
            return [text.slice(0, index), text.slice(index + 1)];
          };
          for (const selector of selectors.specs) {
            for (const el of document.querySelectorAll(selector)) {
              const pair = splitParameterText(el.innerText || '');
              if (pair) addParameter(pair[0], pair[1]);
              if (productParameters.length >= 100) break;
            }
            if (productParameters.length >= 100) break;
          }
          for (const section of document.querySelectorAll('.Ptable-item, [class*="Ptable"], [class*="parameter"], [class*="Parameter"]')) {
            const group = clean(section.querySelector('h3, h4, .Ptable-tit')?.innerText || '');
            for (const row of section.querySelectorAll('dl, tr, li')) {
              const name = clean(row.querySelector('dt, th, .name, [class*="name"]')?.innerText || '');
              const value = clean(row.querySelector('dd, td, .value, [class*="value"]')?.innerText || '');
              if (name && value) addParameter(name, value, group);
              const pair = splitParameterText(row.innerText || '');
              if (pair) addParameter(pair[0], pair[1], group);
              if (productParameters.length >= 100) break;
            }
            if (productParameters.length >= 100) break;
          }
          const textOf = (root, selectorList) => {
            for (const selector of selectorList) {
              const el = root.querySelector(selector);
              const text = clean(el?.innerText || el?.textContent || '', 1200);
              if (text) return text;
            }
            return '';
          };
          const helpfulCount = (text) => {
            text = clean(text, 2000);
            const patterns = [
              /(\d+)\s*(?:人)?(?:点赞|赞|有用|认为有用)/,
              /(?:点赞|赞|有用|认为有用)\D{0,8}(\d+)/
            ];
            for (const pattern of patterns) {
              const match = text.match(pattern);
              if (match) return Number(match[1]);
            }
            return null;
          };
          const positiveTerms = ['好用', '满意', '推荐', '不错', '很好', '超香', '方便', '简单', '值得', '性价比', '喜欢', '大品牌', '香甜', '粒粒分明'];
          const negativeTerms = ['不满意', '不好用', '差评', '很差', '垃圾', '失望', '后悔', '退货', '坏了', '破损', '异味', '夹生', '粘锅', '溢锅', '太慢', '噪音', '漏水', '不推荐'];
          const reviewNodes = [];
          const reviewNodeSeen = new Set();
          for (const selector of selectors.review_items) {
            for (const node of document.querySelectorAll(selector)) {
              if (reviewNodeSeen.has(node)) continue;
              reviewNodeSeen.add(node);
              reviewNodes.push(node);
              if (reviewNodes.length >= 80) break;
            }
            if (reviewNodes.length >= 80) break;
          }
          const reviews = [];
          const reviewSeen = new Set();
          for (const node of reviewNodes) {
            const allText = clean(node.innerText || node.textContent || '', 2000);
            let content = textOf(node, selectors.review_content);
            if (!content) content = allText;
            const user = textOf(node, selectors.review_user);
            const time = textOf(node, selectors.review_time);
            const variant = textOf(node, selectors.review_variant);
            content = clean(content.replace(user, '').replace(time, '').replace(variant, ''), 800);
            if (content.length < 8) continue;
            const key = `${user}\u0000${content}`;
            if (reviewSeen.has(key)) continue;
            reviewSeen.add(key);
            const positive = positiveTerms.some((term) => content.includes(term));
            const negative = negativeTerms.some((term) => content.includes(term));
            reviews.push({
              user: clean(user, 80),
              content,
              helpful_count: helpfulCount(allText),
              time: clean(time, 80),
              variant: clean(variant, 160),
              sentiment: negative ? 'negative' : (positive ? 'positive' : '')
            });
          }
          const reviewSort = (a, b) => (b.helpful_count || 0) - (a.helpful_count || 0);
          const highPraiseReviews = reviews
            .filter((review) => review.sentiment === 'positive')
            .sort(reviewSort)
            .slice(0, 5);
          const highDissatisfiedReviews = reviews
            .filter((review) => review.sentiment === 'negative')
            .sort(reviewSort)
            .slice(0, 5);
          const images = [];
          const ogImage = document.querySelector('meta[property="og:image"]')?.content;
          if (ogImage) images.push(ogImage);
          for (const img of document.querySelectorAll('img')) {
            const src = img.getAttribute('data-origin') || img.getAttribute('data-src') || img.getAttribute('data-lazy-img') || img.src;
            const w = img.naturalWidth || img.width || 0;
            const h = img.naturalHeight || img.height || 0;
            if (src && (w >= 200 || h >= 200)) images.push(src);
            if (images.length >= 30) break;
          }
          const bodyText = document.body?.innerText || '';
          return {
            title: firstText(selectors.title),
            price_text: firstText(selectors.price),
            shop: firstText(selectors.shop),
            review_text: firstText(selectors.reviews),
            sales_text: firstText(selectors.sales),
            specs,
            product_parameters: productParameters,
            high_praise_reviews: highPraiseReviews,
            high_dissatisfied_reviews: highDissatisfiedReviews,
            images,
            json_ld: jsonLd,
            meta: {
              og_title: document.querySelector('meta[property="og:title"]')?.content || '',
              description: document.querySelector('meta[name="description"]')?.content || document.querySelector('meta[property="og:description"]')?.content || '',
              canonical: document.querySelector('link[rel="canonical"]')?.href || ''
            },
            body_text: bodyText
          };
        }
        """,
        selectors,
    )

    json_product = _find_product_json_ld(raw.get("json_ld", []))
    title = compact_text(
        raw.get("title")
        or raw.get("meta", {}).get("og_title")
        or json_product.get("name"),
        500,
    )
    price_text = compact_text(raw.get("price_text"), 120)
    if not price_text:
        offers = json_product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            price_text = compact_text(str(offers.get("price") or offers.get("lowPrice") or ""))

    images: list[str] = []
    json_images = json_product.get("image")
    if isinstance(json_images, str):
        images.append(json_images)
    elif isinstance(json_images, list):
        images.extend(str(item) for item in json_images if item)
    images.extend(str(item) for item in raw.get("images", []) if item)

    normalized_images: list[str] = []
    seen: set[str] = set()
    for image in images:
        normalized = normalize_url(page.url, image)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_images.append(normalized)
        if len(normalized_images) >= 15:
            break

    specs = []
    seen_specs: set[str] = set()
    for spec in raw.get("specs", []):
        cleaned = compact_text(spec, 500)
        if cleaned and cleaned not in seen_specs:
            seen_specs.add(cleaned)
            specs.append(cleaned)
        if len(specs) >= 50:
            break

    body_text = raw.get("body_text") or ""
    product_parameters = _normalize_parameters(raw.get("product_parameters", []))
    if not product_parameters:
        product_parameters = _fallback_parameters_from_text(body_text)
    high_praise_reviews = _normalize_reviews(raw.get("high_praise_reviews", []))
    high_dissatisfied_reviews = _normalize_reviews(
        raw.get("high_dissatisfied_reviews", [])
    )
    if not high_praise_reviews:
        high_praise_reviews = _fallback_reviews_from_text(body_text, positive=True)
    if not high_dissatisfied_reviews:
        high_dissatisfied_reviews = _fallback_reviews_from_text(body_text, positive=False)

    return {
        "platform": platform,
        "url": page.url,
        "title": title,
        "price": parse_price(price_text),
        "price_text": price_text,
        "shop": compact_text(raw.get("shop"), 200),
        "review_text": compact_text(raw.get("review_text"), 120),
        "sales_text": compact_text(raw.get("sales_text"), 120),
        "description": compact_text(raw.get("meta", {}).get("description"), 1200),
        "canonical_url": normalize_url(page.url, raw.get("meta", {}).get("canonical")),
        "specifications": specs,
        "product_parameters": product_parameters,
        "high_praise_reviews": high_praise_reviews,
        "high_dissatisfied_reviews": high_dissatisfied_reviews,
        "images": normalized_images,
        "page_text_excerpt": compact_text(raw.get("body_text"), 10_000),
        "json_ld_product": _limit_json_value(json_product),
    }


def _selectors(platform: str) -> dict[str, list[str]]:
    if platform == "jd":
        return {
            "title": [".sku-name", "#name h1", "h1", "meta[property='og:title']"],
            "price": [
                ".p-price .price",
                ".summary-price .price",
                "[class*='price'] [class*='price']",
                "[class*='price']",
            ],
            "shop": [".name a", ".shop-name", "[class*='shopName']", "[class*='shop-name']"],
            "reviews": [".comment-count .count", "#comment-count", "[class*='comment']"],
            "sales": ["[class*='sales']", "[class*='deal']"],
            "specs": ["#detail .p-parameter-list li", ".parameter2 li", ".Ptable-item", "[class*='parameter'] li"],
            "review_items": [".comment-item", ".J-comment-item", "[class*='comment-item']", "[class*='CommentItem']"],
            "review_user": [".user-info", ".nickname", "[class*='user']", "[class*='User']"],
            "review_content": [".comment-con", ".comment-content", "[class*='content']", "[class*='Content']"],
            "review_time": [".order-info", ".comment-time", "[class*='time']", "[class*='Time']"],
            "review_variant": [".order-info", ".comment-column", "[class*='sku']", "[class*='Sku']"],
        }
    return {
        "title": ["h1", "[class*='Title']", "[class*='title'] h1", "meta[property='og:title']"],
        "price": [
            ".tb-rmb-num",
            "[class*='Price']",
            "[class*='price']",
            "[data-testid*='price']",
        ],
        "shop": [".shop-name", "[class*='Shop']", "[class*='shop'] [class*='name']"],
        "reviews": ["[class*='review']", "[class*='comment']"],
        "sales": ["[class*='sales']", "[class*='sold']", "[class*='deal']"],
        "specs": ["[class*='Parameter'] li", "[class*='parameter'] li", ".attributes-list li", ".tb-attributes li"],
        "review_items": ["[class*='review-item']", "[class*='comment-item']", "[class*='ReviewItem']", "[class*='CommentItem']"],
        "review_user": ["[class*='user']", "[class*='User']", "[class*='nick']", "[class*='Nick']"],
        "review_content": ["[class*='content']", "[class*='Content']", "[class*='review']", "[class*='comment']"],
        "review_time": ["[class*='time']", "[class*='Time']", "[class*='date']", "[class*='Date']"],
        "review_variant": ["[class*='sku']", "[class*='Sku']", "[class*='spec']", "[class*='Spec']"],
    }


def _normalize_parameters(items: list[Any]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = compact_text(str(item.get("name") or ""), 120)
        value = compact_text(str(item.get("value") or ""), 500)
        group = compact_text(str(item.get("group") or ""), 120)
        if not name or not value:
            continue
        key = (group, name, value)
        if key in seen:
            continue
        seen.add(key)
        output.append({"name": name, "value": value, "group": group})
        if len(output) >= 80:
            break
    return output


def _normalize_reviews(items: list[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        user = compact_text(str(item.get("user") or ""), 80)
        content = compact_text(str(item.get("content") or ""), 800)
        if not content:
            continue
        key = (user, content)
        if key in seen:
            continue
        seen.add(key)
        helpful_count = item.get("helpful_count")
        if not isinstance(helpful_count, int):
            helpful_count = None
        output.append(
            {
                "user": user,
                "content": content,
                "helpful_count": helpful_count,
                "time": compact_text(str(item.get("time") or ""), 80),
                "variant": compact_text(str(item.get("variant") or ""), 160),
            }
        )
        if len(output) >= 5:
            break
    return output


def _fallback_parameters_from_text(text: str | None) -> list[dict[str, str]]:
    text = compact_text(text, 20_000)
    if not text:
        return []

    output: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(name: str, value: str, group: str = "") -> None:
        name = compact_text(name, 120)
        value = compact_text(value, 500)
        group = compact_text(group, 120)
        if not name or not value:
            return
        key = (name, value)
        if key in seen:
            return
        seen.add(key)
        output.append({"name": name, "value": value, "group": group})

    breadcrumb = _between(text, "\u6700\u8fd1\u611f\u5174\u8da3 ", " \u8fdb\u5e97\u901b\u901b")
    if breadcrumb:
        add("\u7c7b\u76ee", breadcrumb, "\u57fa\u672c\u4fe1\u606f")

    shop_match = re.search(r">\s*([^ >]{2,40}(?:\u65d7\u8230\u5e97|\u81ea\u8425\u5e97|\u5b98\u65b9\u5e97))", text)
    if shop_match:
        add("\u5e97\u94fa", shop_match.group(1), "\u57fa\u672c\u4fe1\u606f")

    for label in (
        "\u7cfb\u5217\u54c1",
        "\u5bb9\u91cf",
        "\u670d\u52a1",
        "\u4eac\u9009\u670d\u52a1",
        "\u9001\u81f3",
    ):
        value = _section_after_label(
            text,
            label,
            stop_labels=(
                "\u7cfb\u5217\u54c1",
                "\u5bb9\u91cf",
                "\u670d\u52a1",
                "\u4eac\u9009\u670d\u52a1",
                "\u767d\u6761\u5206\u671f",
                "\u6e29\u99a8\u63d0\u793a",
                "\u6536\u85cf",
                "\u00a5",
            ),
        )
        if value:
            add(label, value, "\u9875\u9762\u53ef\u89c1\u53c2\u6570")
        if len(output) >= 20:
            break

    return output[:20]


def _fallback_reviews_from_text(text: str | None, *, positive: bool) -> list[dict[str, Any]]:
    text = compact_text(text, 30_000)
    if not text:
        return []

    start_token = "\u4e70\u5bb6\u8bc4\u4ef7"
    start = text.find(start_token)
    if start < 0:
        return []
    end = _first_existing_index(
        text,
        ("\u5168\u90e8\u8bc4\u4ef7", "\u95ee\u5927\u5bb6", "\u5546\u54c1\u8be6\u60c5"),
        start + len(start_token),
    )
    review_text = text[start:end] if end > start else text[start : start + 6_000]

    user_pattern = r"(?:[A-Za-z0-9_\u4e00-\u9fff]{1,12}\*{1,4}[A-Za-z0-9_\u4e00-\u9fff]{0,12}|[\u4e00-\u9fffA-Za-z0-9_]{2,24})"
    matches = list(re.finditer(rf"\s({user_pattern})\s+", review_text))
    positive_terms = _positive_terms()
    negative_terms = _negative_terms()
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for index, match in enumerate(matches):
        user = compact_text(match.group(1), 80)
        if user in {
            "\u4e70\u5bb6\u8bc4\u4ef7",
            "\u8d85",
            "\u64cd\u4f5c\u8d85\u4fbf\u6377",
            "\u5bb9\u91cf\u591f\u5bb6\u5ead\u7528",
        }:
            continue
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(review_text)
        content = compact_text(review_text[content_start:content_end], 800)
        if len(content) < 12:
            continue
        has_negative = any(term in content for term in negative_terms)
        has_positive = any(term in content for term in positive_terms)
        if positive and has_negative:
            continue
        if not positive and not has_negative:
            continue
        if positive and not has_positive and output:
            continue
        key = (user, content)
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "user": user,
                "content": content,
                "helpful_count": None,
                "time": "",
                "variant": "",
            }
        )
        if len(output) >= 5:
            break

    return output


def _positive_terms() -> tuple[str, ...]:
    return (
        "\u597d\u7528",
        "\u6ee1\u610f",
        "\u63a8\u8350",
        "\u4e0d\u9519",
        "\u5f88\u597d",
        "\u65b9\u4fbf",
        "\u7b80\u5355",
        "\u503c\u5f97",
        "\u6027\u4ef7\u6bd4",
        "\u559c\u6b22",
        "\u9999",
        "\u6e05\u6d17",
        "\u987a\u624b",
    )


def _negative_terms() -> tuple[str, ...]:
    return (
        "\u4e0d\u6ee1\u610f",
        "\u4e0d\u597d\u7528",
        "\u5dee\u8bc4",
        "\u5f88\u5dee",
        "\u5931\u671b",
        "\u540e\u6094",
        "\u9000\u8d27",
        "\u574f\u4e86",
        "\u7834\u635f",
        "\u5f02\u5473",
        "\u5939\u751f",
        "\u7c98\u9505",
        "\u6ea2\u9505",
        "\u592a\u6162",
        "\u566a\u97f3",
        "\u6f0f\u6c34",
        "\u4e0d\u63a8\u8350",
    )


def _between(text: str, start_token: str, end_token: str) -> str:
    start = text.find(start_token)
    if start < 0:
        return ""
    start += len(start_token)
    end = text.find(end_token, start)
    if end < 0:
        return ""
    return compact_text(text[start:end], 500)


def _section_after_label(
    text: str, label: str, *, stop_labels: tuple[str, ...]
) -> str:
    start = text.find(f" {label} ")
    if start < 0:
        start = text.find(label)
    if start < 0:
        return ""
    start += len(label)
    end = _first_existing_index(text, tuple(item for item in stop_labels if item != label), start)
    if end <= start:
        end = min(len(text), start + 500)
    return compact_text(text[start:end], 500)


def _first_existing_index(text: str, tokens: tuple[str, ...], start: int) -> int:
    indexes = [text.find(token, start) for token in tokens]
    indexes = [index for index in indexes if index >= 0]
    return min(indexes) if indexes else len(text)


def _find_product_json_ld(nodes: list[Any]) -> dict[str, Any]:
    queue: list[Any] = list(nodes)
    while queue:
        node = queue.pop(0)
        if isinstance(node, list):
            queue.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        node_type = node.get("@type")
        if node_type == "Product" or (
            isinstance(node_type, list) and "Product" in node_type
        ):
            return node
        graph = node.get("@graph")
        if isinstance(graph, list):
            queue.extend(graph)
    return {}


def _limit_json_value(value: Any, depth: int = 0) -> Any:
    """Bound JSON-LD size before returning it through MCP."""
    if depth >= 4:
        if isinstance(value, (dict, list)):
            return "[truncated]"
        return compact_text(str(value), 500)
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 30:
                output["_truncated"] = True
                break
            output[str(key)] = _limit_json_value(item, depth + 1)
        return output
    if isinstance(value, list):
        output = [_limit_json_value(item, depth + 1) for item in value[:20]]
        if len(value) > 20:
            output.append("[truncated]")
        return output
    if isinstance(value, str):
        return compact_text(value, 1200)
    return value
