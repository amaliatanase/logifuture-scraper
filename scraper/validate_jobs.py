"""Generic job URL validator (content-aware, manual use).

Mirrors the JS template's ``scraper/validate-jobs.js``.

PURPOSE: deep validation of job URLs -- fetches the full page body and scans
for "no longer available" / "position filled" / "expired" keywords. Slower
than a HEAD-only check but catches soft-404s where the URL still returns 200
but the job is gone.

SCOPE: generic -- works with any CIF, a single URL, or a list from a file.
For ad-hoc cleanup and debugging; not called from CI.

Usage:
    python -m scraper.validate_jobs <CIF>                    - query Solr and validate all jobs for a CIF
    python -m scraper.validate_jobs --url <url>               - check a single URL
    python -m scraper.validate_jobs --urls <url1> <url2> ...  - check multiple URLs
    python -m scraper.validate_jobs --file <file.json>        - check URLs from a JSON file (array or {"jobs": [...]})
    python -m scraper.validate_jobs <CIF> --delete             - also delete expired jobs from Solr
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import api
from .config import OWN_URL_PREFIX
from .job_validator import validate_by_content


def _is_own_job(url: str) -> bool:
    """The same CIF can carry jobs from OTHER peviitor scrapers / aggregators
    (eJobs, BestJobs imports, etc.) -- query_solr(cif) returns all of them,
    but delete_expired_jobs must only ever touch the ones THIS scraper owns.
    """
    return isinstance(url, str) and url.startswith(OWN_URL_PREFIX)

HELP = """
Job URL Validator

Usage:
  python -m scraper.validate_jobs <CIF>                    - Query Solr and validate all jobs for a company
  python -m scraper.validate_jobs --url <url>              - Check a single URL
  python -m scraper.validate_jobs --urls <url1> <url2> ... - Check multiple URLs
  python -m scraper.validate_jobs --file <file.json>       - Check URLs from a JSON file

Examples:
  python -m scraper.validate_jobs 12345678
  python -m scraper.validate_jobs --url "https://jobs.example.com/careers/some-job/"
  python -m scraper.validate_jobs --urls "url1" "url2" "url3"
  python -m scraper.validate_jobs --file jobs.json
"""


def check_urls(urls: list[str]) -> dict[str, list[dict]]:
    print(f"=== Validating {len(urls)} URLs ===\n")
    results: dict[str, list[dict]] = {"active": [], "expired": [], "error": []}

    for i, url in enumerate(urls, 1):
        result = validate_by_content(url)
        results[result["status"]].append(result)

        icon = {"active": "OK", "expired": "EXPIRED", "error": "ERROR"}[result["status"]]
        print(f"[{icon}] [{i}/{len(urls)}] {result['status']} (HTTP {result['httpStatus']}) - {url}")
        if result["title"]:
            print(f"   Title: {result['title'][:60]}...")
        if result["error"]:
            print(f"   Error: {result['error']}")

    print("\n=== SUMMARY ===")
    print(f"Total: {len(urls)}")
    print(f"Active: {len(results['active'])}")
    print(f"Expired: {len(results['expired'])}")
    print(f"Error: {len(results['error'])}")
    return results


def validate_jobs(cif: str) -> dict[str, list[dict]]:
    print("=== Validate Job URLs from Solr ===\n")
    result = api.query_solr(cif)
    urls = [doc["url"] for doc in result["docs"]]
    print(f"Found {len(urls)} jobs for CIF {cif}\n")
    return check_urls(urls)


def load_urls_from_file(file_path: str) -> list[str]:
    data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item if isinstance(item, str) else item["url"] for item in data]
    if isinstance(data, dict) and "jobs" in data:
        return [job["url"] if isinstance(job, dict) else job for job in data["jobs"]]
    if isinstance(data, dict) and "urls" in data:
        return data["urls"]
    raise ValueError("Unknown file format. Expected an array of URLs or {'jobs': [...]}")


def delete_expired_jobs(expired_jobs: list[dict]) -> None:
    ours = [job for job in expired_jobs if _is_own_job(job["url"])]
    not_ours = [job for job in expired_jobs if not _is_own_job(job["url"])]
    if not_ours:
        print(f"\n{len(not_ours)} expired job(s) belong to another scraper on this CIF -- never touched:")
        for job in not_ours:
            print(f"  {job['url']}")

    print(f"\nDeleting {len(ours)} expired jobs from Solr...")
    for job in ours:
        print(f"Deleting: {job['url']}")
        api.delete_job_by_url(job["url"])
    print("Done.")


def _parse_args(argv: list[str]) -> dict:
    if not argv:
        return {"mode": "cif", "cif": None}
    mode = argv[0]
    if mode == "--url" and len(argv) > 1:
        return {"mode": "single", "urls": [argv[1]]}
    if mode == "--urls":
        return {"mode": "multiple", "urls": argv[1:]}
    if mode == "--file" and len(argv) > 1:
        return {"mode": "file", "filePath": argv[1]}
    if not mode.startswith("--"):
        return {"mode": "cif", "cif": mode}
    return {"mode": "help"}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parsed = _parse_args(argv)
    mode = parsed["mode"]

    if mode == "help":
        print(HELP)
        return 0

    if mode in ("single", "multiple"):
        check_urls(parsed["urls"])
        return 0

    if mode == "file":
        check_urls(load_urls_from_file(parsed["filePath"]))
        return 0

    if mode == "cif" and parsed.get("cif"):
        results = validate_jobs(parsed["cif"])
        if results["expired"]:
            if "--delete" in argv:
                delete_expired_jobs(results["expired"])
            else:
                print("\nPass --delete to remove expired jobs from Solr")
                output = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "cif": parsed["cif"],
                    "summary": {
                        "total": len(results["active"]) + len(results["expired"]) + len(results["error"]),
                        "active": len(results["active"]),
                        "expired": len(results["expired"]),
                        "error": len(results["error"]),
                    },
                    "expiredJobs": [{"url": j["url"], "title": j["title"]} for j in results["expired"]],
                    "errorJobs": [{"url": j["url"], "error": j["error"]} for j in results["error"]],
                }
                Path("tmp").mkdir(parents=True, exist_ok=True)
                Path("tmp/expired-jobs.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
                print("Saved tmp/expired-jobs.json")
        return 0

    print(HELP)
    return 1


if __name__ == "__main__":
    sys.exit(main())
