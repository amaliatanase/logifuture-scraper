"""Integration tests against the real ANAF/CUIScan and peviitor APIs.

Not part of the default `pytest -q` unit run's expectations in spirit -- they
self-skip (rather than fail) whenever either (a) the config is still the
template's own `{{PLACEHOLDER}}` values (nothing real to look up yet) or
(b) the network isn't reachable, so CI for the *template itself* stays green.
Once a company derives this template and fills in config/company.json, these
start doing real work -- mirrors the reference Python template's
tests/integration/test_company_real.py.
"""

from __future__ import annotations

import socket
import time

import pytest

from scraper import anaf, api
from scraper.config import company as company_config

COMPANY_CIF = company_config["id"]
COMPANY_NAME = company_config["company"]

# These hit real, occasionally-flaky third-party services (ANAF/CUIScan,
# our own peviitor API over the public internet from a CI runner). anaf.py
# itself deliberately makes exactly one attempt per source before cascading
# (see test_anaf.py::test_anaf_calls_are_single_attempt_no_retry -- that is
# correct for production, where a slow retry loop would hold up the whole
# scrape run). This test layer is different: it exists only to sanity-check
# connectivity in CI, so it retries the *whole* call a few times with a
# short delay, and skips (never fails the build) if every attempt errors
# out or the network is unreachable -- a transient outage on someone else's
# API is not a bug in this repository.
_RETRY_ATTEMPTS = 3
_RETRY_DELAY_SEC = 2.0


def _is_placeholder(value: str) -> bool:
    return isinstance(value, str) and value.startswith("{{")


def _reachable(host: str, port: int = 443, timeout: float = 3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _with_retries(label: str, fn, attempts: int = _RETRY_ATTEMPTS, delay: float = _RETRY_DELAY_SEC):
    """Call ``fn()`` up to ``attempts`` times, skipping the test (not failing
    it) if every attempt raises -- see module docstring above."""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - any failure is retried, then skipped
            last_exc = exc
            if i < attempts - 1:
                time.sleep(delay)
    pytest.skip(f"{label} unavailable after {attempts} attempts: {last_exc}")


@pytest.fixture(autouse=True)
def _skip_until_derived():
    if _is_placeholder(COMPANY_CIF) or _is_placeholder(COMPANY_NAME):
        pytest.skip("template not yet derived -- config/company.json still has {{PLACEHOLDER}} values")


def test_anaf_returns_the_configured_company():
    if not (_reachable("demoanaf.ro") or _reachable("cuiscan.ro")):
        pytest.skip("neither demoanaf.ro nor cuiscan.ro reachable")
    data = _with_retries("ANAF/CUIScan", lambda: anaf.get_company_from_anaf(COMPANY_CIF))
    if not data:
        pytest.skip("ANAF/CUIScan returned no data")
    assert str(data.get("cui")) == str(COMPANY_CIF)


def test_peviitor_solr_query_succeeds():
    host = api.API_BASE.split("://", 1)[1].split("/", 1)[0]
    if not _reachable(host):
        pytest.skip(f"{host} not reachable")
    result = _with_retries("peviitor SOLR", lambda: api.query_solr(COMPANY_CIF))
    assert "numFound" in result
    assert "docs" in result
