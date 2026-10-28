"""Validates the LIVE peviitor company-core record for this scraper's CIF
against COMPANY_MODEL_FIELDS. This is a consistency check on peviitor's
data, not on our own code -- it exists because a stale or malformed
company-core record is otherwise invisible until someone notices the
site's company filter behaving oddly (see the 2026-09-24 Hochland
investigation: a case-sensitivity bug meant this endpoint silently never
matched, and a fleet-adjacent scraper's company record sat stale for
weeks with nothing to flag it). Mirrors the JS template's
tests/consistency/company-model.test.js.
"""

from __future__ import annotations

import requests

from scraper.company import COMPANY_CIF, COMPANY_MODEL_FIELDS, validate_company_model

# True only in the Brewtality-3-16 template itself, where setup.py hasn't
# filled in a real CIF yet -- never in a derived repo.
IS_TEMPLATE_CHECKOUT = "{{" in COMPANY_CIF


def _fetch_live_company_record() -> dict | None:
    res = requests.get(
        f"https://api.peviitor.ro/v1/firme/company/?cif={COMPANY_CIF}",
        headers={"User-Agent": "pytest"},
        timeout=10.0,
    )
    if not res.ok:
        return None
    data = res.json().get("data") or []
    return data[0] if data else None


def test_company_model_fields_declares_id_and_company_as_required():
    required = [f["name"] for f in COMPANY_MODEL_FIELDS if f["required"]]
    assert "id" in required
    assert "company" in required


def test_live_company_core_record_matches_the_model():
    if IS_TEMPLATE_CHECKOUT:
        print("running in the Brewtality-3-16 template itself (CIF not yet filled in) -- skipping live check")
        return

    try:
        record = _fetch_live_company_record()
    except requests.RequestException as exc:
        print(f"could not reach api.peviitor.ro ({exc}) -- skipping live check")
        return

    if not record:
        print(f"no live company-core record yet for CIF {COMPANY_CIF} -- skipping")
        return

    result = validate_company_model(record)
    if result["extra_fields"]:
        print(f"note: extra fields on live record (not in model): {result['extra_fields']}")
    if not result["valid"]:
        print("live company record validation errors:")
        for e in result["errors"]:
            print(f"  - {e}")
    assert result["valid"], result["errors"]


def test_live_record_id_matches_this_scrapers_configured_cif():
    if IS_TEMPLATE_CHECKOUT:
        print("running in the Brewtality-3-16 template itself (CIF not yet filled in) -- skipping live check")
        return

    try:
        record = _fetch_live_company_record()
    except requests.RequestException as exc:
        print(f"could not reach api.peviitor.ro ({exc}) -- skipping live check")
        return

    if not record:
        print(f"no live company-core record yet for CIF {COMPANY_CIF} -- skipping")
        return

    assert record["id"] == COMPANY_CIF
