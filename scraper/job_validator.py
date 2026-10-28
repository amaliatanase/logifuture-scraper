"""Job URL validation primitives — shared by CI cleanup and the manual CLI.

Mirrors the JS template's ``scraper/job-validator.js``:

- ``validate_by_head(url)``    -- fast HEAD check, only HTTP status matters.
- ``validate_by_content(url)`` -- GET the page and scan the body for
  expiration keywords (catches soft-404s where status is 200 but the job
  is gone).
- ``validate_by_browser(url)`` -- headless Chromium via Playwright, for
  JS-rendered 404 text. Optional dependency: falls back to
  ``validate_by_content`` if Playwright isn't installed.
"""

from __future__ import annotations

import logging
import re

import requests

from .config import USER_AGENT

log = logging.getLogger("scraper.job_validator")

DEFAULT_EXPIRED_KEYWORDS = [
    "sorry, this position is no longer available",
    "position is no longer available",
    "job is no longer available",
    "this vacancy is no longer available",
    "no longer accepting applications",
    "this position has been filled",
    "job expired",
    "the page you are looking for doesn't exist",
]

DEFAULT_TIMEOUT_SEC = 15.0
_TITLE_RX = re.compile(r"<title>([^<]+)</title>", re.I)


def _result(url: str, status: str, http_status: int = 0, title: str | None = None, error: str | None = None) -> dict:
    return {"url": url, "status": status, "httpStatus": http_status, "title": title, "error": error}


def validate_by_head(url: str, *, user_agent: str = USER_AGENT) -> dict:
    """HEAD-only validator. active if 2xx/3xx, expired otherwise. Fast."""
    try:
        res = requests.head(url, headers={"User-Agent": user_agent}, allow_redirects=True, timeout=DEFAULT_TIMEOUT_SEC)
        return _result(url, "active" if res.ok else "expired", res.status_code)
    except requests.RequestException as exc:
        return _result(url, "error", error=str(exc))


def validate_by_content(
    url: str,
    *,
    keywords: list[str] | None = None,
    user_agent: str = USER_AGENT,
    timeout: float = DEFAULT_TIMEOUT_SEC,
) -> dict:
    """Full GET + body scan. Catches soft-404s (HTTP 200, page says "no longer
    available") *and* hard 404s whose body doesn't match any keyword (a site's
    real "not found" page rarely uses these exact phrases) -- a non-2xx/3xx
    status is unambiguous evidence the page is gone, independent of what its
    body says."""
    keywords = keywords if keywords is not None else DEFAULT_EXPIRED_KEYWORDS
    try:
        res = requests.get(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            allow_redirects=True,
            timeout=timeout,
        )
        text = res.text or ""
        lower = text.lower()
        expired = not res.ok or any(kw in lower for kw in keywords)
        title_match = _TITLE_RX.search(text)
        return _result(url, "expired" if expired else "active", res.status_code, title_match.group(1).strip() if title_match else None)
    except requests.RequestException as exc:
        return _result(url, "error", error=str(exc))


def validate_by_browser(
    url: str,
    *,
    keywords: list[str] | None = None,
    timeout_ms: int = int(DEFAULT_TIMEOUT_SEC * 1000),
) -> dict:
    """Headless-browser validator via Playwright (optional dependency).

    Install with ``pip install -e ".[browser]"``
    (or ``pip install playwright && playwright install chromium``). Falls back
    to :func:`validate_by_content` if Playwright is not installed.
    """
    keywords = keywords if keywords is not None else DEFAULT_EXPIRED_KEYWORDS
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        log.debug("playwright not installed -- falling back to validate_by_content for %r", url)
        return validate_by_content(url, keywords=keywords)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = browser.new_page()
                response = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                text = page.inner_text("body")
                title = page.title()
            finally:
                browser.close()
        status = response.status if response is not None else 200
        lower = text.lower()
        expired = status >= 400 or any(kw in lower for kw in keywords)
        return _result(url, "expired" if expired else "active", status, title or None)
    except Exception as exc:  # noqa: BLE001 - any browser failure is reported, not fatal
        if "Executable doesn't exist" in str(exc):
            # playwright is installed but `playwright install chromium` was never run
            log.debug("chromium not installed -- falling back to validate_by_content for %r", url)
            return validate_by_content(url, keywords=keywords)
        return _result(url, "error", error=str(exc))
