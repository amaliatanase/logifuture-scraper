"""Pre-publish data validation + the 0-result canary.

"Bad data is worse than missing data" — a job with an empty title or a garbage
URL pollutes the peviitor index and is hard to clean up later. Generic: the
rules are peviitor-wide, not site-specific.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

log = logging.getLogger("scraper.validate")

MAX_TITLE_LEN = 200
_HTML_TAG = re.compile(r"<[a-z][\s\S]*>", re.I)
# a "-" that starts the string or follows whitespace / "(" / ":" is a real
# negative sign; a "-" between two digits ("5000-8000") is a range separator.
_NEGATIVE = re.compile(r"(?:^|[\s(:])-\s*\d")


class CanaryError(RuntimeError):
    """Raised when a run scraped nothing — abort before writing anything."""


def validate_job(job: object) -> tuple[bool, list[str]]:
    """Return ``(is_valid, errors)`` for one raw scraped job dict."""
    errors: list[str] = []

    if not isinstance(job, dict):
        return False, ["job is not a dict"]

    url = job.get("url")
    if not isinstance(url, str) or url.strip() == "":
        errors.append("url is empty")
    else:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            errors.append(f"url is not a valid URL: {url}")
        elif parsed.scheme not in ("http", "https"):
            errors.append(f"url has non-http(s) scheme: {parsed.scheme}")

    title = job.get("title")
    if not isinstance(title, str) or title.strip() == "":
        errors.append("title is empty")
    else:
        if _HTML_TAG.search(title):
            errors.append("title contains HTML")
        if len(title.strip()) > MAX_TITLE_LEN:
            errors.append(f"title exceeds {MAX_TITLE_LEN} chars")

    location = job.get("location")
    if location is not None:
        if not isinstance(location, list):
            errors.append("location is not a list")
        elif any(not isinstance(loc, str) or loc.strip() == "" for loc in location):
            errors.append("location has an empty entry")

    salary = job.get("salary")
    if salary is not None:
        if not isinstance(salary, str):
            errors.append("salary is not a string")
        elif _NEGATIVE.search(salary):
            errors.append(f"salary has a negative amount: {salary}")

    return (len(errors) == 0), errors


def filter_valid_jobs(jobs: list[dict]) -> tuple[list[dict], list[tuple[dict, list[str]]]]:
    """Split jobs into ``(kept, dropped)``; log every rejection."""
    kept: list[dict] = []
    dropped: list[tuple[dict, list[str]]] = []

    for job in jobs:
        ok, errors = validate_job(job)
        if ok:
            kept.append(job)
        else:
            dropped.append((job, errors))
            log.warning(
                'dropped "%s" (%s): %s',
                job.get("title", "?") if isinstance(job, dict) else "?",
                job.get("url", "no url") if isinstance(job, dict) else "no url",
                "; ".join(errors),
            )

    if dropped:
        log.warning("%d/%d job(s) failed validation and were dropped", len(dropped), len(jobs))
    return kept, dropped


def assert_scrape_yielded_jobs(jobs_or_count: list | int) -> int:
    """Canary — throw before any write when the scrape produced nothing.

    A 0-result run almost always means the markup changed, not that the company
    genuinely has zero openings.
    """
    count = len(jobs_or_count) if isinstance(jobs_or_count, (list, tuple)) else int(jobs_or_count)
    if not count:
        raise CanaryError(
            "canary: 0 jobs scraped from all sources — aborting before any write "
            "(a broken listing selector is far more likely than a company with no jobs)"
        )
    return count
