"""Company validation + a small file cache for ANAF data.

Mirrors the JS template's ``scraper/company.js``: validate the company via
ANAF (through ``scraper.anaf``), fall back to a cached copy when ANAF is
unreachable, and check the company's status in peviitor's own index.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from . import anaf, api
from .config import USER_AGENT, company as company_config

log = logging.getLogger("scraper.company")

PEVIITOR_COMPANY_URL = "https://api.peviitor.ro/v1/company/"

COMPANY_CIF = company_config["id"]
COMPANY_BRAND = company_config.get("brand")
COMPANY_LEGAL_NAME = company_config["company"]

CACHE_MAX_AGE_DAYS = 7
ROOT_CACHE_PATH = Path("company.json")
TMP_CACHE_PATH = Path("tmp/company.json")

# ============================================================================
# COMPANY MODEL - schema for the peviitor company-core document
# ============================================================================

#: Declarative schema for a peviitor company-core document, mirrored from
#: what scrape-reusable.yml's upsert step writes and from
#: api.peviitor.ro/v1/company/'s response shape. Mirrors the JS template's
#: COMPANY_MODEL_FIELDS (scraper/company.js) field for field. Used by
#: validate_company_model() so a consistency test can assert the *live*
#: record still has the fields/types/status the fleet relies on, instead of
#: only checking that our own upsert payload looked right.
COMPANY_MODEL_FIELDS: list[dict[str, Any]] = [
    {"name": "id", "required": True, "type": "string"},
    {"name": "company", "required": True, "type": "string"},
    {"name": "brand", "required": False, "type": "string"},
    {"name": "group", "required": False, "type": "string"},
    {"name": "status", "required": False, "type": "string", "allowed": ["activ", "suspendat", "inactiv", "radiat"]},
    {"name": "location", "required": False, "type": "array"},
    {"name": "website", "required": False, "type": "array"},
    {"name": "career", "required": False, "type": "array"},
    {"name": "lastScraped", "required": False, "type": "string"},
    {"name": "scraperFile", "required": False, "type": "string"},
]


def validate_company_model(data: dict | None) -> dict[str, Any]:
    """Validate a company-core document against COMPANY_MODEL_FIELDS.

    Returns ``{"valid": bool, "errors": [str, ...], "extra_fields": [str, ...]}``.
    """
    if not isinstance(data, dict):
        return {"valid": False, "errors": ["No company document provided"], "extra_fields": []}

    errors: list[str] = []
    for field in COMPANY_MODEL_FIELDS:
        name = field["name"]
        value = data.get(name)

        if field["required"] and (value is None or value == ""):
            errors.append(f"Missing required field: {name}")
            continue
        if value is None:
            continue

        if field["type"] == "string" and not isinstance(value, str):
            errors.append(f"Field {name} should be string, got {type(value).__name__}")
        if field["type"] == "array" and not isinstance(value, list):
            errors.append(f"Field {name} should be array, got {type(value).__name__}")
        allowed = field.get("allowed")
        if allowed and value not in allowed:
            errors.append(f"Field {name} has invalid value {value!r}. Allowed: {', '.join(allowed)}")

    allowed_fields = {f["name"] for f in COMPANY_MODEL_FIELDS}
    extra_fields = [k for k in data.keys() if k not in allowed_fields]

    return {"valid": not errors, "errors": errors, "extra_fields": extra_fields}


def _get_company_from_peviitor(company_name: str) -> dict | None:
    res = requests.get(
        PEVIITOR_COMPANY_URL,
        params={"name": company_name},
        headers={
            "origin": "https://peviitor.ro",
            "referer": "https://peviitor.ro/",
            "User-Agent": USER_AGENT,
        },
        timeout=10.0,
    )
    if not res.ok:
        raise RuntimeError(f"Peviitor API error: {res.status_code}")
    companies = res.json().get("companies") or []
    return companies[0] if companies else None


def _save_company_data(anaf_data: dict | None, peviitor_data: dict | None) -> dict:
    summary = {
        "company": (anaf_data or {}).get("name"),
        "cif": str((anaf_data or {}).get("cui")) if (anaf_data or {}).get("cui") is not None else None,
        "active": not (anaf_data or {}).get("inactive"),
        "inactiveSince": (anaf_data or {}).get("inactiveSince"),
        "address": (anaf_data or {}).get("address"),
    }
    company_data = {
        "validatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "ANAF",
        "brand": COMPANY_BRAND,
        "anaf": anaf_data,
        "peviitor": peviitor_data,
        "summary": summary,
    }
    text = json.dumps(company_data, indent=2, ensure_ascii=False)

    TMP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TMP_CACHE_PATH.write_text(text, encoding="utf-8")
    log.info("saved company data to %s", TMP_CACHE_PATH)

    ROOT_CACHE_PATH.write_text(text, encoding="utf-8")
    log.info("updated root cache %s", ROOT_CACHE_PATH)

    return company_data


def _is_valid_cache(data: dict | None) -> bool:
    anaf_data = (data or {}).get("anaf") or {}
    return bool(anaf_data.get("cui") and anaf_data.get("name"))


def _is_cache_fresh(data: dict) -> bool:
    validated_at = data.get("validatedAt")
    if not validated_at:
        return False
    try:
        validated = datetime.fromisoformat(validated_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    age_days = (datetime.now(timezone.utc) - validated).total_seconds() / 86400
    return age_days < CACHE_MAX_AGE_DAYS


def _load_cached_company_data() -> dict | None:
    for cache_path in (TMP_CACHE_PATH, ROOT_CACHE_PATH):
        if not cache_path.exists():
            continue
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            log.warning("could not parse %s", cache_path)
            continue
        if not _is_valid_cache(data):
            continue
        if _is_cache_fresh(data):
            log.info("found fresh cached company data in %s", cache_path)
            return data
        log.info("found stale cached company data in %s (older than %d days)", cache_path, CACHE_MAX_AGE_DAYS)
        return {**data, "_stale": True}
    return None


def get_company_data() -> dict[str, Any]:
    """Company identity, ANAF-first with a cache fallback. See module docstring."""
    cached_data = _load_cached_company_data()

    if cached_data and not cached_data.get("_stale") and (cached_data.get("summary") or {}).get("cif"):
        anaf_data = cached_data["anaf"]
        log.info("using cached company data for CIF %s", cached_data["summary"]["cif"])
        log.info("cached name: %s / status: %s", anaf_data["name"], "INACTIVE" if anaf_data.get("inactive") else "ACTIVE")
        return {
            "company": anaf_data["name"].upper(),
            "cif": str(anaf_data["cui"]),
            "active": not anaf_data.get("inactive"),
            "anafData": anaf_data,
        }

    log.info("fetching fresh company data from ANAF for CIF %s", COMPANY_CIF)
    try:
        anaf_data = anaf.get_company_from_anaf(COMPANY_CIF)
    except Exception as exc:  # noqa: BLE001 - both ANAF sources failed
        cached_anaf = (cached_data or {}).get("anaf")
        if cached_anaf:
            log.warning("ANAF unreachable (%s) — falling back to cached data", exc)
            return {
                "company": cached_anaf["name"].upper(),
                "cif": str(cached_anaf["cui"]),
                "active": not cached_anaf.get("inactive"),
                "anafData": cached_anaf,
            }
        log.warning("ANAF unreachable (%s) — no cache available, proceeding with company config", exc)
        return {"company": COMPANY_LEGAL_NAME, "cif": str(COMPANY_CIF), "active": True, "anafData": None}

    if not anaf_data:
        raise RuntimeError("No data from ANAF - cannot proceed with scraping")
    if not anaf_data.get("name"):
        raise RuntimeError("ANAF returned no company name - cannot proceed with scraping")

    log.info("ANAF returned name: %s / status: %s", anaf_data["name"], "INACTIVE" if anaf_data.get("inactive") else "ACTIVE")
    return {
        "company": anaf_data["name"].upper(),
        "cif": str(anaf_data["cui"]),
        "active": not anaf_data.get("inactive"),
        "anafData": anaf_data,
    }


def validate_and_get_company(*, dry_run: bool = False) -> dict[str, Any]:
    """Full validation workflow: ANAF -> SOLR check -> peviitor check -> cache.

    ``dry_run`` must reach all the way here: an ANAF-inactive company below
    triggers ``delete_jobs_by_cif`` -- a real, CIF-wide DELETE against
    peviitor's live API that removes every job under that CIF, including
    ones scraped by other, unrelated scrapers -- and this function used to
    fire it unconditionally, with no way for a caller to ask for a safe,
    read-only check. `main.run(dry_run=True)` calling this with no
    `dry_run` of its own meant a plain `--dry-run` invocation against a
    company ANAF reports inactive would still mass-delete real, live jobs.
    """
    log.info("=== Step 1: Validate company via ANAF ===")
    data = get_company_data()
    company_name, cif, active, anaf_data = data["company"], data["cif"], data["active"], data["anafData"]

    log.info("=== Step 2: Check existing jobs in SOLR ===")
    solr_result = api.query_solr(cif)
    log.info("jobs found in SOLR for CIF %s: %d", cif, solr_result["numFound"])

    log.info("=== Step 3: Validate via Peviitor ===")
    peviitor_data = None
    try:
        # Peviitor's own search is an exact, case-sensitive match against
        # the legal name it already has stored (uppercase) -- querying
        # with the brand (e.g. "Hochland" against a stored "HOCHLAND ...")
        # never matches, so this silently returned no record, and every
        # job/company write below fell back to ANAF's freshly fetched name
        # instead of whatever peviitor already had indexed.
        peviitor_data = _get_company_from_peviitor(COMPANY_LEGAL_NAME.upper())
        log.info("peviitor data fetched successfully")
    except Exception as exc:  # noqa: BLE001 - best-effort, non-fatal
        log.info("peviitor API error: %s", exc)

    if anaf_data:
        _save_company_data(anaf_data, peviitor_data)

    # Prefer the name peviitor already has on file for this CIF: ANAF's
    # spelling (diacritics, spacing) can drift from what's already indexed
    # and faceted on the site, and peviitor's company-core upsert does not
    # reliably rewrite an existing "company" field -- so a job tagged with
    # ANAF's fresh name can permanently mismatch the site's "Companie"
    # filter even though free-text search still finds it. Only fall back
    # to ANAF's name for a company peviitor has never seen before.
    if peviitor_data and peviitor_data.get("company"):
        company_name = peviitor_data["company"]

    if not active:
        if dry_run:
            log.warning(
                "company is INACTIVE in ANAF -- dry-run, so NOT deleting the %d job(s) "
                "under this CIF (would run delete_jobs_by_cif on a real run)",
                solr_result["numFound"],
            )
        else:
            log.warning("company is INACTIVE in ANAF - deleting jobs from SOLR and stopping")
            if solr_result["numFound"] > 0:
                api.delete_jobs_by_cif(cif)
        return {"status": "inactive", "company": company_name, "cif": cif, "existingJobsCount": solr_result["numFound"]}

    address = (anaf_data or {}).get("address") or ""
    log.info("company validated: %s, CIF: %s", company_name, cif)
    return {
        "status": "active",
        "company": company_name,
        "cif": cif,
        "existingJobsCount": solr_result["numFound"],
        "address": address,
        "anafData": anaf_data,
    }
