"""Rendering layer: static fetch vs. headless browser (Playwright).

The unit tests inject a fake ``sync_playwright`` so they run anywhere. The one
``browser``-marked test drives a real Chromium against a ``data:`` URL (no
network) and is skipped when Playwright or its browser binaries are missing.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from urllib.parse import quote

import pytest

from scraper import browser, fetch


# ---------------------------------------------------------------- fakes
class _Page:
    def __init__(self, log, html):
        self.log, self.html = log, html

    def goto(self, url, **kw):
        self.log.append(("goto", url, kw))

    def wait_for_selector(self, sel, **kw):
        self.log.append(("wait", sel, kw))

    def content(self):
        return self.html


class _Browser:
    def __init__(self, log, html):
        self.log, self.html = log, html

    def new_context(self, **kw):
        self.log.append(("context", kw))
        return self

    def new_page(self):
        return _Page(self.log, self.html)

    def close(self):
        self.log.append(("close",))


def fake_playwright(log, html="<html>rendered</html>", launch_error=None):
    @contextmanager
    def sync_playwright():
        class _PW:
            class chromium:  # noqa: N801
                @staticmethod
                def launch():
                    if launch_error:
                        raise launch_error
                    return _Browser(log, html)
        yield _PW
    return sync_playwright


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def static_get(monkeypatch):
    calls = []

    def _get(url, **kw):
        calls.append(url)
        return _Resp("<html>static</html>")
    monkeypatch.setattr(fetch, "get", _get)
    return calls


# ---------------------------------------------------------------- render_html
def test_render_html_returns_dom_waits_and_closes():
    log = []
    html = browser.render_html("https://x.test/jobs", wait_selector=".job", timeout_ms=1234,
                               sync_playwright=fake_playwright(log))
    assert html == "<html>rendered</html>"
    assert ("goto", "https://x.test/jobs", {"wait_until": "networkidle", "timeout": 1234}) in log
    assert ("wait", ".job", {"timeout": 1234}) in log
    assert log[-1] == ("close",)


def test_render_html_closes_browser_when_navigation_fails():
    log = []
    pw = fake_playwright(log)

    class Boom(_Page):
        def goto(self, url, **kw):
            raise TimeoutError("nav timeout")
    orig = _Browser.new_page
    _Browser.new_page = lambda self: Boom(self.log, "")
    try:
        with pytest.raises(TimeoutError):
            browser.render_html("https://x.test", sync_playwright=pw)
    finally:
        _Browser.new_page = orig
    assert ("close",) in log


def test_missing_binaries_become_browser_unavailable():
    err = RuntimeError("BrowserType.launch: Executable doesn't exist at /x. Please run: playwright install")
    with pytest.raises(browser.BrowserUnavailable):
        browser.render_html("https://x.test", sync_playwright=fake_playwright([], launch_error=err))


def test_missing_playwright_package_is_browser_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(browser.BrowserUnavailable):
        browser.render_html("https://x.test")


# ---------------------------------------------------------------- get_html
def test_static_mode_never_launches_a_browser(static_get):
    def boom(*a, **k):
        raise AssertionError("browser must not be used in static mode")
    assert browser.get_html("https://x.test", mode="static", render=boom) == "<html>static</html>"
    assert static_get == ["https://x.test"]


def test_browser_mode_skips_the_static_fetch(static_get):
    assert browser.get_html("https://x.test", mode="browser", render=lambda url: "DOM") == "DOM"
    assert static_get == []


def test_auto_keeps_static_html_when_it_has_jobs(static_get):
    out = browser.get_html("https://x.test", mode="auto", parse_ok=lambda h: True,
                           render=lambda url: pytest.fail("should not render"))
    assert out == "<html>static</html>"


def test_auto_renders_when_static_html_has_no_jobs(static_get):
    out = browser.get_html("https://x.test", mode="auto", parse_ok=lambda h: False, render=lambda url: "DOM")
    assert out == "DOM"


def test_auto_falls_back_to_static_when_browser_unavailable(static_get):
    def unavailable(url):
        raise browser.BrowserUnavailable("no chromium")
    out = browser.get_html("https://x.test", mode="auto", parse_ok=lambda h: False, render=unavailable)
    assert out == "<html>static</html>"


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError):
        browser.get_html("https://x.test", mode="turbo")


def test_shipped_config_defaults_to_static():
    assert browser.MODE == "static"


# ---------------------------------------------------------------- live Chromium
@pytest.mark.browser
def test_real_chromium_sees_javascript_rendered_content():
    pytest.importorskip("playwright.sync_api")
    page = ("<div id=a></div><script>document.getElementById('a').textContent='rendered-by-js'</script>")
    try:
        html = browser.render_html("data:text/html," + quote(page), wait_selector="#a", timeout_ms=15000)
    except browser.BrowserUnavailable:
        pytest.skip("chromium not installed (playwright install chromium)")
    assert "rendered-by-js" in html