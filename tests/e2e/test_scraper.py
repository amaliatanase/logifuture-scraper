"""End-to-end test: scrape the real careers page configured in config/scraper.json.

Self-skips (rather than fails) while this is still the template itself (the
careers URL is still a `{{PLACEHOLDER}}`) or when the site isn't reachable, so
CI for the template stays green. Once a company derives this template and
points the placeholders at a real site, this starts doing real work --
mirrors the reference Python template's tests/e2e/test_scraper.py.
"""

from __future__ import annotations

import socket
from urllib.parse import urlparse

import pytest

from scraper.config import scraper
from scraper.main import scrape_careers

LISTING_URL = scraper["sources"]["listing"]


def _is_placeholder(value: str) -> bool:
    return isinstance(value, str) and value.startswith("{{")


def _reachable(host: str, port: int = 443, timeout: float = 5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def test_scrape_real_careers_page():
    if _is_placeholder(LISTING_URL):
        pytest.skip("template not yet derived -- config/scraper.json still has a {{PLACEHOLDER}} careers URL")

    host = urlparse(LISTING_URL).netloc
    if not host or not _reachable(host):
        pytest.skip(f"{host or LISTING_URL} not reachable")

    jobs = scrape_careers()
    assert jobs, "expected at least one job from the real careers page"

    urls = {j["url"] for j in jobs}
    assert len(urls) == len(jobs), "duplicate job URLs found"
    for job in jobs:
        assert job["title"]
        assert job["url"].startswith("http")
