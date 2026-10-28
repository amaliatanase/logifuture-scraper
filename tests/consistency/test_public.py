"""Consistency test: the repository must be PUBLIC.

Mirrors the JS template's tests/consistency/public.test.js. Skips (rather
than fails) when GITHUB_REPOSITORY isn't set -- i.e. when run locally, not
in CI -- exactly like the JS version.
"""

from __future__ import annotations

import os

import pytest
import requests

REPO = os.environ.get("GITHUB_REPOSITORY")
TOKEN = os.environ.get("GITHUB_TOKEN")


def test_repository_must_be_public():
    if not REPO:
        pytest.skip("GITHUB_REPOSITORY not set -- running locally, skipping API check")

    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "pytest"}
    if TOKEN:
        headers["Authorization"] = f"token {TOKEN}"

    res = requests.get(f"https://api.github.com/repos/{REPO}", headers=headers, timeout=10)
    assert res.ok, f"GitHub API error: {res.status_code} - {res.text}"

    data = res.json()
    assert data["private"] is False
    assert data["visibility"] == "public"
