from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须是整数，当前值为 {raw!r}") from exc
    return max(minimum, min(value, maximum))


@dataclass(frozen=True, slots=True)
class Settings:
    headless: bool
    browser_channel: str | None
    profile_dir: Path
    artifacts_dir: Path
    navigation_timeout_ms: int
    action_timeout_ms: int
    action_delay_ms: int
    slow_mo_ms: int
    max_page_text_chars: int
    max_search_results: int
    allow_state_changing_actions: bool
    proxy: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        channel = os.getenv("BROWSER_CHANNEL", "").strip() or None
        proxy = os.getenv("PROXY", "").strip() or None
        profile_dir = Path(
            os.getenv(
                "BROWSER_PROFILE_DIR",
                "~/.jd-taobao-browser-mcp/browser-profile",
            )
        ).expanduser()
        artifacts_dir = Path(
            os.getenv(
                "ARTIFACTS_DIR",
                "~/.jd-taobao-browser-mcp/artifacts",
            )
        ).expanduser()

        return cls(
            headless=_env_bool("PLAYWRIGHT_HEADLESS", False),
            browser_channel=channel,
            profile_dir=profile_dir,
            artifacts_dir=artifacts_dir,
            navigation_timeout_ms=_env_int(
                "NAVIGATION_TIMEOUT_MS", 45_000, 5_000, 180_000
            ),
            action_timeout_ms=_env_int("ACTION_TIMEOUT_MS", 15_000, 2_000, 60_000),
            action_delay_ms=_env_int("ACTION_DELAY_MS", 700, 0, 10_000),
            slow_mo_ms=_env_int("SLOW_MO_MS", 80, 0, 2_000),
            max_page_text_chars=_env_int(
                "MAX_PAGE_TEXT_CHARS", 18_000, 1_000, 100_000
            ),
            max_search_results=_env_int("MAX_SEARCH_RESULTS", 30, 1, 100),
            allow_state_changing_actions=_env_bool(
                "ALLOW_STATE_CHANGING_ACTIONS", False
            ),
            proxy=proxy,
        )
