"""Page fetching with optional headless-browser rendering (Playwright).

Most career sites are server-rendered and ``fetch.get`` is enough (the default,
``rendering.mode = "static"``). Sites that build their job list in JavaScript
(React/Algolia/SuccessFactors search, ...) return an empty shell to ``requests``;
for those set in ``config/scraper.json``::

    "rendering": {"mode": "browser", "waitSelector": ".job-card", "timeoutMs": 30000}

``"auto"`` tries the static fetch first and only renders in a browser when the
caller's ``parse_ok`` says the static HTML had no jobs, so a site that starts
client-rendering later keeps working instead of silently returning 0 jobs.

Playwright is imported lazily: a derived scraper that never leaves ``static``
mode does not need browsers installed (``playwright install chromium``).
"""

from __future__ import annotations

import logging
from typing import Callable

from . import fetch
from .config import USER_AGENT, scraper

log = logging.getLogger("scraper.browser")

_R = scraper.get("rendering") or {}
MODE: str = _R.get("mode", "static")
WAIT_SELECTOR: str | None = _R.get("waitSelector") or None
TIMEOUT_MS: int = int(_R.get("timeoutMs", 30000))

VALID_MODES = ("static", "browser", "auto")


class BrowserUnavailable(RuntimeError):
    """Playwright (or its browser binaries) is not installed / cannot launch."""


def render_html(url: str, *, wait_selector: str | None = None, timeout_ms: int | None = None,
                sync_playwright=None) -> str:
    """Return the DOM of ``url`` after JavaScript has run.

    ``sync_playwright`` is injectable for tests; production leaves it ``None``.
    """
    if sync_playwright is None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError as exc:
            raise BrowserUnavailable("playwright is not installed (pip install playwright)") from exc

    wait_selector = wait_selector if wait_selector is not None else WAIT_SELECTOR
    timeout = timeout_ms if timeout_ms is not None else TIMEOUT_MS

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_context(user_agent=USER_AGENT).new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout)
                if wait_selector:
                    page.wait_for_selector(wait_selector, timeout=timeout)
                return page.content()
            finally:
                browser.close()
    except BrowserUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - launch failures (missing binaries) surface here
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
            raise BrowserUnavailable("chromium is not installed (playwright install chromium)") from exc
        raise


def get_html(url: str, *, label: str = "page", mode: str | None = None,
             parse_ok: Callable[[str], bool] | None = None,
             render: Callable[..., str] = render_html) -> str:
    """Fetch ``url`` according to the configured rendering mode.

    ``parse_ok(html)`` tells ``auto`` mode whether the static HTML already holds
    what the caller needs; if it is falsy the page is rendered in a browser.
    """
    mode = mode or MODE
    if mode not in VALID_MODES:
        raise ValueError(f"rendering.mode must be one of {VALID_MODES}, got {mode!r}")

    if mode == "browser":
        return render(url)

    resp = fetch.get(url, label=label)
    resp.raise_for_status()
    html = resp.text

    if mode == "auto" and parse_ok is not None and not parse_ok(html):
        log.info("%s: static HTML had no jobs, rendering in a browser", label)
        try:
            return render(url)
        except BrowserUnavailable as exc:
            log.warning("%s: %s -- keeping the static HTML", label, exc)
    return html