from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

_PRICE_RE = re.compile(r"(?:¥|￥|RMB|CNY)?\s*([0-9]+(?:\.[0-9]{1,2})?)")


def compact_text(value: str | None, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if limit is not None and len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def parse_price(value: str | None) -> float | None:
    if not value:
        return None
    normalized = value.replace(",", "")
    match = _PRICE_RE.search(normalized)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def normalize_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("//"):
        return "https:" + href
    return urljoin(base_url, href)


def dedupe_dicts(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        raw = item.get(key)
        if not raw:
            continue
        token = str(raw)
        if token in seen:
            continue
        seen.add(token)
        output.append(item)
    return output
