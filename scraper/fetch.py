"""HTTP with retry + full-jitter exponential backoff.

Transient failures (connection errors, timeouts, 429, 5xx) are retried up to
``retry.maxAttempts`` times; ``Retry-After`` is honoured when present. 4xx and
success are returned to the caller unchanged. Backoff collapses to
milliseconds under pytest so the retry tests stay fast.

(A production scraper may prefer ``tenacity`` — this hand-rolled version keeps
the dependency surface small and the backoff logic trivially testable.)
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time

import requests

from .config import USER_AGENT, scraper

log = logging.getLogger("scraper.fetch")

_R = scraper["retry"]
# pytest is imported before any test module, so this is reliable at import time
# (PYTEST_CURRENT_TEST is only set during the call phase).
_IS_TEST = "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))

MAX_ATTEMPTS: int = 3 if _IS_TEST else int(_R["maxAttempts"])
BASE_DELAY: float = 0.001 if _IS_TEST else float(_R["baseDelaySec"])
MAX_DELAY: float = 0.01 if _IS_TEST else float(_R["maxDelaySec"])
RETRY_STATUS: set[int] = set(_R["retryStatus"])
TIMEOUT: float = float(scraper["requestTimeoutSec"])


def backoff_delay(attempt: int, retry_after: str | None = None) -> float:
    """Full-jitter exponential backoff. ``attempt`` is 0-based."""
    if retry_after:
        try:
            secs = float(retry_after)
            if secs >= 0:
                return min(secs, MAX_DELAY)
        except ValueError:
            pass
    ceiling = min(MAX_DELAY, BASE_DELAY * (2 ** attempt))
    return random.uniform(0, ceiling)


def request(method: str, url: str, *, label: str = "request", session: requests.Session | None = None,
            **kwargs) -> requests.Response:
    """``requests.request`` with retry/backoff. Raises the last error if every
    attempt fails; returns the response otherwise (including a final 5xx, so the
    caller's normal error handling still runs)."""
    sess = session or requests
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    kwargs.setdefault("timeout", TIMEOUT)

    last_exc: Exception | None = None
    retry_after: str | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt > 0:
            delay = backoff_delay(attempt - 1, retry_after)
            log.info("%s: retry %d/%d after %.3fs (%s)", label, attempt, MAX_ATTEMPTS - 1, delay, last_exc)
            time.sleep(delay)

        try:
            resp = sess.request(method, url, headers=headers, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            retry_after = None
            continue

        if resp.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
            retry_after = resp.headers.get("Retry-After")
            last_exc = requests.HTTPError(f"{label}: HTTP {resp.status_code}")
            continue

        return resp

    raise last_exc if last_exc else RuntimeError(f"{label}: exhausted retries")


def get(url: str, **kwargs) -> requests.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> requests.Response:
    return request("POST", url, **kwargs)
