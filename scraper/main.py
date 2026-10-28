"""Orchestration: fetch -> parse (self-healing) -> validate -> canary -> upsert -> diff.

Deliberately small; the interesting logic lives in the modules it calls.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import api, browser, fetch, job_validator
from . import company as company_validation
from .config import COMPANY_CIF, OWN_URL_PREFIX, company, scraper
from .markdown_generator import generate_jobs_markdown
from .parse import (
    iso_z,
    location_from_title,
    normalize_workmode,
    parse_deadline,
    parse_listing,
    slugify,
    validate_ro_locations,
)
from .validate import assert_scrape_yielded_jobs, filter_valid_jobs

log = logging.getLogger("scraper.main")

# Collapsed to ~0 under pytest, same trick as scraper.fetch's own retry delays --
# PYTEST_CURRENT_TEST is only set during the call phase, but "pytest" is already
# imported by the time any test module runs, so this is reliable at import time.
_IS_TEST = "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))
_SOLR_SETTLE_DELAY_SEC = 0.001 if _IS_TEST else 2.0

_LOC_RX = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")

# The path segment that marks an individual job permalink, derived from
# ``ownJobUrlPrefix`` (e.g. "https://site.com/jobs/" -> "/jobs/").
try:
    _JOB_PATH = urlparse(OWN_URL_PREFIX).path.rstrip("/") + "/"
except Exception:  # noqa: BLE001
    _JOB_PATH = "/"
_JOB_PERMALINK_RX = re.compile(re.escape(_JOB_PATH) + r"[^/]+/?$")

try:
    _CAREERS_SOURCE = urlparse(scraper["sources"]["listing"]).netloc or "careers-site"
except Exception:  # noqa: BLE001
    _CAREERS_SOURCE = "careers-site"


def _is_own(url: str) -> bool:
    return isinstance(url, str) and url.startswith(OWN_URL_PREFIX)


def fetch_sitemap_job_urls() -> list[dict]:
    sitemap_url = scraper["sources"]["sitemap"]
    if not sitemap_url or sitemap_url.startswith("{{"):  # not configured
        return []
    try:
        resp = fetch.get(sitemap_url, label="sitemap")
        if not resp.ok:
            log.info("sitemap returned %d", resp.status_code)
            return []
        entries = []
        for m in _LOC_RX.finditer(resp.text):
            url = m.group(1).strip()
            if not _JOB_PERMALINK_RX.search(url):
                continue
            entries.append({"url": url, "slug": url.rstrip("/").split("/")[-1]})
        log.info("sitemap: %d job permalinks", len(entries))
        return entries
    except Exception as exc:  # noqa: BLE001
        log.info("sitemap error: %s", exc)
        return []


def _match_sitemap_url_exact(title: str, entries: list[dict]) -> str | None:
    slug = slugify(title)
    for e in entries:
        if e["slug"] == slug:
            return e["url"]
    return None


def _match_sitemap_url_fuzzy(title: str, entries: list[dict]) -> str | None:
    """Bounded-prefix fallback: tolerates a "-2"/"-copy" disambiguation
    suffix on the SAME job. Deliberately separate from the exact match above
    and always tried second, run-wide, across every item (see
    scrape_careers) -- a fuzzy match can't tell a same-job suffix apart from
    a genuinely different posting whose slug happens to extend another
    job's, so an exact match anywhere in this run must win that sitemap slot
    over a fuzzy one, regardless of which title the listing puts first."""
    slug = slugify(title)
    for e in entries:
        a, b = e["slug"], slug
        if a.startswith(b) and a[len(b):len(b) + 1] == "-":
            return e["url"]
        if b.startswith(a) and b[len(a):len(a) + 1] == "-":
            return e["url"]
    return None


def scrape_careers() -> list[dict]:
    listing_url = scraper["sources"]["listing"]
    log.info("scraping %s ...", listing_url)
    entries = fetch_sitemap_job_urls()

    try:
        html = browser.get_html(listing_url, label="listing", parse_ok=lambda h: bool(parse_listing(h)))
        items = parse_listing(html)
    except Exception as exc:  # noqa: BLE001
        log.info("listing error: %s", exc)
        items = []

    jobs: list[dict] = []
    if items:
        archive = scraper["sources"]["jobArchive"]

        # Resolve every item's URL in two passes so an exact sitemap match
        # always wins a shared slug over a fuzzy one, regardless of which
        # title the listing happens to put first:
        #   pass 1 -- the scraped <a href> (ground truth) or an EXACT sitemap
        #             slug match; these are trustworthy, so claim their URLs
        #             immediately.
        #   pass 2 -- only the items pass 1 couldn't resolve try the fuzzy
        #             bounded-prefix fallback, and only win an unclaimed URL.
        # Without this ordering, a longer, unrelated title that fuzzy-matches
        # an earlier position in `entries` could claim a sitemap URL before
        # the job that's an exact match for it even gets a turn -- e.g.
        # "Reprezentant Medical si Vanzari - Veterinare" (no sitemap entry of
        # its own, no anchor in the listing) grabbing "reprezentant-medical"
        # ahead of the real "Reprezentant Medical" posting. Two jobs sharing
        # one URL means one silently overwrites the other in SOLR.
        resolved: dict[int, str] = {}
        claimed_sitemap_urls: set[str] = set()
        unresolved: list[int] = []
        for i, item in enumerate(items):
            # The real <a href> scraped from the page is ground truth -- prefer
            # it over guessing. Sites whose permalink needs an ID the title
            # can't reproduce (e.g. "/jobs/jr133930/software-architect/")
            # silently 404 under the guess, which nothing else catches until
            # job_validator's HEAD check below.
            scraped_url = item.get("url")
            if scraped_url:
                resolved[i] = urljoin(listing_url, scraped_url)
                continue
            exact = _match_sitemap_url_exact(item["title"], entries)
            if exact:
                resolved[i] = exact
                claimed_sitemap_urls.add(exact)
            else:
                unresolved.append(i)

        for i in unresolved:
            fuzzy = _match_sitemap_url_fuzzy(items[i]["title"], entries)
            if fuzzy and fuzzy not in claimed_sitemap_urls:
                resolved[i] = fuzzy
                claimed_sitemap_urls.add(fuzzy)
            else:
                # Either no fuzzy match, or it points at a sitemap URL an
                # exact match already claimed this run -- guess instead. A
                # wrong guess 404s and _drop_dead_urls removes it: a safe
                # failure (job missing this run) instead of an unsafe one
                # (two jobs merged into one).
                resolved[i] = f"{archive}{slugify(items[i]['title'])}/"

        for i, item in enumerate(items):
            jobs.append({
                "url": resolved[i],
                "title": item["title"],
                "location": location_from_title(item["title"], scraper["defaultLocation"]),
                "workmode": scraper["defaultWorkmode"],
                "expirationdate": item.get("expirationdate"),
                "source": _CAREERS_SOURCE,
            })
    elif entries:
        log.info("listing unreachable -- sitemap-only fallback (titles from slugs)")
        for e in entries:
            jobs.append({
                "url": e["url"],
                "title": e["slug"].replace("-", " ").title(),
                "location": scraper["defaultLocation"],
                "workmode": scraper["defaultWorkmode"],
                "source": _CAREERS_SOURCE,
            })

    log.info("found %d jobs on %s", len(jobs), _CAREERS_SOURCE)
    return jobs


def search_anofm(cif: str) -> list[dict]:
    """Free public postings for this CIF from ANOFM (the state employment
    agency), in addition to the company's own careers site. Port of
    scraper-js's ``searchANOFM`` -- the Python template shipped without this
    supplementary source since it was first written, even though the README
    always documented both variants as targeting "a Romanian company's own
    careers site + ANOFM". These are never treated as ``ownJobUrlPrefix``
    jobs (they live under mediere.anofm.ro), so they're purely additive and
    never touched by stale-job deletion.
    """
    jobs: list[dict] = []
    try:
        payload = {
            "current": 1,
            "rowCount": 250,
            "sort": {"created_at": "desc"},
            "employer_tax_code": cif,
        }
        resp = fetch.post(
            "https://mediere.anofm.ro/api/entity/vw_public_job_posting",
            label="anofm",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        if not resp.ok:
            log.info("ANOFM returned %d", resp.status_code)
            return jobs
        data = resp.json()
        for row in data.get("rows") or []:
            parts = [p.strip() for p in (row.get("address_locality_name") or "").split(">")]
            location = parts[-1] if len(parts) > 1 else (parts[0] if parts else "")
            job_id = row.get("id")
            if not job_id or not row.get("occupation"):
                continue
            jobs.append({
                "url": f"https://mediere.anofm.ro/app/module/mediere/job/{job_id}",
                "title": row["occupation"],
                "location": [location] if location else None,
                "source": "ANOFM",
            })
        log.info("found %d jobs on ANOFM", len(jobs))
    except Exception as exc:  # noqa: BLE001 - best-effort supplementary source
        log.info("ANOFM error: %s", exc)
    return jobs


def _drop_dead_urls(jobs: list[dict]) -> list[dict]:
    """Pre-upload safety net: GET-check every job URL and drop the ones that
    don't resolve. ``validate.py`` only checks URL *shape* (a syntactically
    valid http(s) URL); job_validator.py can actually tell a live job from a
    404, but nothing called it before an upload -- this is what let a
    URL-construction bug reach peviitor undetected.

    Uses ``validate_by_content`` (GET), not ``validate_by_head``: at least one
    real careers site (Workday-based) answers every HEAD request with a
    generic 404 regardless of whether the resource exists (`Allow: GET` in
    the response) -- HEAD-only would have dropped every real job."""
    alive: list[dict] = []
    for job in jobs:
        result = job_validator.validate_by_content(job["url"])
        if result["status"] == "active":
            alive.append(job)
        else:
            log.warning(
                'dropped "%s" (%s): live URL check failed -- %s',
                job.get("title", "?"), job.get("url", "?"),
                result.get("error") or f"HTTP {result.get('httpStatus')}",
            )
    if len(alive) < len(jobs):
        log.warning("%d/%d job(s) failed live URL validation and were dropped", len(jobs) - len(alive), len(jobs))
    return alive


def _to_job_model(raw: dict, cif: str, company_name: str) -> dict:
    job = {
        "url": raw["url"],
        "title": raw["title"],
        "company": company_name,
        "cif": cif,
        "location": validate_ro_locations(raw.get("location")),
        "workmode": normalize_workmode(raw.get("workmode")),
        "expirationdate": raw.get("expirationdate") or None,
        "date": iso_z(datetime.now(timezone.utc)),
        "status": "scraped",
    }
    return {k: v for k, v in job.items() if v is not None}


def _write_docs(company_name: str, cif: str, address: str, jobs: list[dict]) -> None:
    """docs/jobs.md + docs/company.json -- the GitHub Pages source for this repo."""
    docs_company_data = {
        "id": cif,
        "company": company_name,
        "brand": company.get("brand"),
        "status": "activ",
        "location": [address] if address else company.get("location"),
        "website": company.get("website"),
        "career": company.get("career"),
        "lastScraped": datetime.now(timezone.utc).date().isoformat(),
    }
    markdown = generate_jobs_markdown(docs_company_data, jobs)

    docs_dir = Path("docs")
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "jobs.md").write_text(markdown, encoding="utf-8")
    log.info("saved docs/jobs.md")

    # company.json = the static company config + the URL prefix the static page
    # uses to show only jobs this scraper manages (not eJobs/BestJobs imports
    # on the same CIF).
    (docs_dir / "company.json").write_text(
        json.dumps({**company, "ownJobUrlPrefix": OWN_URL_PREFIX}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("wrote docs/company.json (+ ownJobUrlPrefix)")


def run(*, dry_run: bool = False) -> int:
    log.info("=== Step 1: existing jobs in SOLR ===")
    existing = api.query_solr(COMPANY_CIF)
    all_existing = {d["url"] for d in existing["docs"]}
    own_existing = {d["url"] for d in existing["docs"] if _is_own(d["url"])}
    log.info("SOLR has %d jobs for this CIF (%d ours)", existing["numFound"], len(own_existing))

    log.info("=== Step 2: validate company via ANAF ===")
    validated = company_validation.validate_and_get_company(dry_run=dry_run)
    company_name = validated["company"]
    cif = validated["cif"]
    address = validated.get("address") or ""

    if validated["status"] == "inactive":
        if dry_run:
            log.warning(
                "company is INACTIVE -- dry-run, so NOT deleting our %d job(s) (would delete "
                "on a real run; validate_and_get_company already skipped the CIF-wide delete)",
                len(own_existing),
            )
        else:
            log.warning("company is INACTIVE -- removing only our own jobs, skipping scrape.")
            for url in own_existing:
                try:
                    api.delete_job_by_url(url)
                except Exception as exc:  # noqa: BLE001 - best-effort cleanup, one bad URL shouldn't abort the rest
                    log.warning("delete failed: %s -- %s", url, exc)
        return 0

    # On by default: upsert_company is an idempotent PUT of ANAF-validated facts
    # (name, address, website, career URL), so there's no real downside to
    # keeping the company core in sync -- unlike staleJobDeletion below, this
    # is additive, not destructive. Only turn it off once you've verified
    # another scraper genuinely owns this CIF's company record.
    #
    # Must be gated on dry_run like every other real write in this function --
    # it wasn't, so a plain `--dry-run` invocation (used throughout this
    # project as a safe, no-write way to sanity-check a freshly derived
    # scraper) was silently PUTting real company data to peviitor's live API
    # the entire time. Nothing destructive went out this way (the payload is
    # always correct, additive ANAF data), but "dry-run" must mean no writes
    # at all, full stop -- a caller relies on that to test safely.
    if scraper.get("manageCompany") and not dry_run:
        try:
            api.upsert_company({
                "id": cif,
                "company": company_name,
                "brand": company.get("brand"),
                "status": "activ",
                "location": [address] if address else scraper["defaultLocation"],
                "website": company.get("website"),
                "career": company.get("career"),
                "scraperFile": company.get("scraperFile"),
                "lastScraped": datetime.now(timezone.utc).date().isoformat(),
            })
        except Exception as exc:  # noqa: BLE001 - non-fatal, matches the JS template
            log.info("could not upsert company: %s", exc)
    elif dry_run and scraper.get("manageCompany"):
        log.info("dry-run -- would upsert company core for CIF %s", cif)
    else:
        log.info(
            "manageCompany=false -- leaving company core untouched (explicitly disabled in "
            "config/scraper.json; only turn this off once you've *verified* another scraper "
            "actually manages this CIF's company record -- an unverified guess here is exactly "
            "what left a real company entirely missing from peviitor's company core before)"
        )

    log.info("=== Step 3: scrape ===")
    raw_jobs = scrape_careers()

    anofm_jobs = search_anofm(cif)
    seen_urls = {j["url"] for j in raw_jobs}
    for job in anofm_jobs:
        if job["url"] not in seen_urls:
            raw_jobs.append(job)
            seen_urls.add(job["url"])
    log.info("jobs from ANOFM: %d", len(anofm_jobs))
    log.info("total jobs scraped (careers site + ANOFM): %d", len(raw_jobs))

    assert_scrape_yielded_jobs(raw_jobs)  # canary
    valid_jobs, _ = filter_valid_jobs(raw_jobs)
    assert_scrape_yielded_jobs(valid_jobs)  # everything failed validation -> also a canary

    jobs = [_to_job_model(j, cif, company_name) for j in valid_jobs]
    jobs = _drop_dead_urls(jobs)

    log.info("=== Step 4: upsert ===")
    if dry_run:
        log.info("dry-run -- would upsert %d jobs", len(jobs))
    elif jobs:
        api.upsert_jobs(jobs)
    else:
        log.info("no live jobs to upsert -- skipping (API rejects an empty array)")

    _write_docs(company_name, cif, address, jobs)

    scraped_urls = {j["url"] for j in jobs}
    added = sorted(scraped_urls - all_existing)
    updated = sorted(scraped_urls & all_existing)
    gone = sorted(own_existing - scraped_urls)

    # Off by default -- deliberately, not by an unverified guess (see AGENTS.md).
    # Deletion is already scoped to ownJobUrlPrefix, so a shared CIF is never
    # actually at risk; the real reason to leave this off is that a *partial*
    # scrape failure (site glitch, a selector that only matches some cards)
    # still passes the canary (jobs > 0) and would otherwise delete real,
    # still-live jobs this run simply failed to find. job-deep-validate.yml
    # (scraper/validate_jobs.py) is the safer way to catch genuinely dead
    # URLs -- it live-checks each one instead of inferring "gone" from a diff.
    if scraper["staleJobDeletion"]:
        if gone:
            log.info("=== Step 4.5: delete %d stale job(s) (ours only) ===", len(gone))
            for url in gone:
                try:
                    log.info("  deleting: %s", url)
                    if not dry_run:
                        api.delete_job_by_url(url)
                except Exception as exc:  # noqa: BLE001 - one failed delete shouldn't abort the rest
                    log.warning("  failed to delete: %s -- %s", url, exc)
        else:
            log.info("no stale jobs to delete")
    else:
        log.info(
            "step 4.5 skipped -- staleJobDeletion=false (deliberate: a partial scrape "
            "failure would otherwise delete real jobs it simply failed to find this run -- "
            "use job-deep-validate.yml to actually confirm and clean up dead URLs)"
        )

    # Give SOLR a moment to settle, then re-query for real -- the summary below
    # must reflect confirmed post-write state, not just what we intended to
    # upsert. A silently-failed or partially-applied write would otherwise be
    # reported as a success.
    time.sleep(_SOLR_SETTLE_DELAY_SEC)
    final = api.query_solr(COMPANY_CIF)

    log.info("=== SUMMARY ===")
    log.info("scraped this run:            %d", len(jobs))
    log.info("  new (not in SOLR before): %d", len(added))
    log.info("  updated (already in SOLR): %d", len(updated))
    log.info("  gone from site (ours):     %d%s", len(gone),
             " — kept (staleJobDeletion=false)" if gone and not scraper["staleJobDeletion"] else "")
    for u in gone[:10]:
        log.info("    - %s", u)
    log.info("jobs in SOLR after scrape:    %d", final["numFound"])
    return len(jobs)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="run the whole flow without writing to the API")
    ns = ap.parse_args()
    run(dry_run=ns.dry_run)
