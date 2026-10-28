"""scraper.job_validator -- HEAD / content / browser URL validation."""

import sys
import requests

from scraper import job_validator as jv


def test_validate_by_head_active_on_2xx(requests_mock):
    requests_mock.head("https://x/jobs/a/", status_code=200)
    result = jv.validate_by_head("https://x/jobs/a/")
    assert result == {"url": "https://x/jobs/a/", "status": "active", "httpStatus": 200, "title": None, "error": None}


def test_validate_by_head_expired_on_404(requests_mock):
    requests_mock.head("https://x/jobs/a/", status_code=404)
    result = jv.validate_by_head("https://x/jobs/a/")
    assert result["status"] == "expired"
    assert result["httpStatus"] == 404


def test_validate_by_head_error_on_network_failure(requests_mock):
    requests_mock.head("https://x/jobs/a/", exc=requests.ConnectionError("boom"))
    result = jv.validate_by_head("https://x/jobs/a/")
    assert result["status"] == "error"
    assert "boom" in result["error"]


def test_validate_by_content_active_when_no_keyword_present(requests_mock):
    requests_mock.get("https://x/jobs/a/", status_code=200, text="<html><title>Great Job</title><body>Apply now</body></html>")
    result = jv.validate_by_content("https://x/jobs/a/")
    assert result["status"] == "active"
    assert result["title"] == "Great Job"


def test_validate_by_content_expired_on_soft_404_keyword(requests_mock):
    requests_mock.get(
        "https://x/jobs/a/",
        status_code=200,
        text="<html><body>Sorry, this position is no longer available.</body></html>",
    )
    result = jv.validate_by_content("https://x/jobs/a/")
    assert result["status"] == "expired"
    assert result["httpStatus"] == 200  # soft-404: HTTP is 200, the body says otherwise


def test_validate_by_content_expired_on_hard_404_even_without_a_keyword_match(requests_mock):
    """A real site's own "not found" page rarely uses any of
    DEFAULT_EXPIRED_KEYWORDS' exact phrasing (confirmed live against
    betfairromania.ro: its 404 page is titled "Page Not Found", matching none
    of them) -- the HTTP status alone must be enough to call it expired."""
    requests_mock.get(
        "https://x/jobs/a/",
        status_code=404,
        text="<html><title>Page Not Found</title><body>Oops, nothing here.</body></html>",
    )
    result = jv.validate_by_content("https://x/jobs/a/")
    assert result["status"] == "expired"
    assert result["httpStatus"] == 404


def test_validate_by_content_error_on_network_failure(requests_mock):
    requests_mock.get("https://x/jobs/a/", exc=requests.Timeout("timed out"))
    result = jv.validate_by_content("https://x/jobs/a/")
    assert result["status"] == "error"


def test_validate_by_browser_falls_back_to_content_when_playwright_missing(requests_mock, monkeypatch):
    # Playwright is imported lazily; when the package is absent we must
    # transparently fall back to validate_by_content -- exactly like the JS template.
    # (Simulated, so the test is hermetic whether or not playwright is installed.)
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    requests_mock.get("https://x/jobs/a/", status_code=200, text="<html><title>T</title><body>ok</body></html>")
    result = jv.validate_by_browser("https://x/jobs/a/")
    assert result["status"] == "active"
    assert result["title"] == "T"


def test_validate_by_browser_falls_back_to_content_when_chromium_not_installed(requests_mock, monkeypatch):
    # Package present but `playwright install chromium` never ran: launch raises
    # "Executable doesn't exist ..." -- fall back instead of reporting an error.
    import types
    from contextlib import contextmanager

    @contextmanager
    def fake_sync_playwright():
        class _PW:
            class chromium:  # noqa: N801
                @staticmethod
                def launch(**kw):
                    raise RuntimeError("BrowserType.launch: Executable doesn't exist at /x")
        yield _PW

    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", types.SimpleNamespace(sync_playwright=fake_sync_playwright))
    requests_mock.get("https://x/jobs/a/", status_code=200, text="<html><title>T</title><body>ok</body></html>")
    result = jv.validate_by_browser("https://x/jobs/a/")
    assert result["status"] == "active"
