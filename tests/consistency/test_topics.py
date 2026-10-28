"""Consistency test: the repository must have EXACTLY the 2 required topics
-- plus, in the template's own checkout only, the extra "scraper-template"
topic that marks it as a template on GitHub (this test used to run
unconditionally and fail on every push to Brewtality-3-16 itself, since the
template legitimately carries 3 topics, not 2 -- caught via a live CI check
during the Faza 4 audit, not by local pytest, which always skips this test
for lack of GITHUB_REPOSITORY).

Mirrors the JS template's tests/consistency/topics.test.js. Skips (rather
than fails) when GITHUB_REPOSITORY isn't set -- i.e. when run locally, not
in CI -- exactly like the JS version.
"""

from __future__ import annotations

import os
import pathlib
import re

import pytest
import requests

REPO = os.environ.get("GITHUB_REPOSITORY")
TOKEN = os.environ.get("GITHUB_TOKEN")

REQUIRED_TOPICS = ["job-seeker-ro-spider", "peviitor-ro"]
TEMPLATE_ONLY_TOPIC = "scraper-template"


def _is_template_checkout() -> bool:
    pyproject = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject.exists():
        return False
    match = re.search(r'^name = "([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
    return bool(match) and match.group(1) == "peviitor-scraper-template"


def test_repository_has_exactly_the_required_topics():
    if not REPO:
        pytest.skip("GITHUB_REPOSITORY not set -- running locally, skipping API check")

    headers = {"Accept": "application/vnd.github.mercy-preview+json", "User-Agent": "pytest"}
    if TOKEN:
        headers["Authorization"] = f"token {TOKEN}"

    res = requests.get(f"https://api.github.com/repos/{REPO}/topics", headers=headers, timeout=10)
    assert res.ok, f"GitHub API error: {res.status_code} - {res.text}"

    topics = sorted(t.lower() for t in res.json().get("names", []))
    expected = sorted(REQUIRED_TOPICS + [TEMPLATE_ONLY_TOPIC]) if _is_template_checkout() else sorted(REQUIRED_TOPICS)
    assert topics == expected, f"expected exactly {expected}, got: {topics}"
