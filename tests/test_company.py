"""Company validation workflow: ANAF-first cache in scraper.company."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scraper import anaf, api, company


@pytest.fixture(autouse=True)
def isolated_cwd(monkeypatch, tmp_path):
    """company.py caches to ./company.json and ./tmp/company.json (CWD-relative)."""
    monkeypatch.chdir(tmp_path)


def _write_cache(path: Path, *, cui="12345678", name="CACHED SRL", inactive=False, validated_at=None):
    validated_at = validated_at or datetime.now(timezone.utc).isoformat()
    data = {
        "validatedAt": validated_at,
        "anaf": {"cui": cui, "name": name, "inactive": inactive, "address": "Str. X 1"},
        "peviitor": None,
        "summary": {"company": name, "cif": cui, "active": not inactive},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def test_get_company_data_fetches_fresh_when_no_cache(monkeypatch):
    monkeypatch.setattr(anaf, "get_company_from_anaf", lambda cif: {"cui": 12345678, "name": "ACME SRL", "inactive": False})
    data = company.get_company_data()
    assert data == {"company": "ACME SRL", "cif": "12345678", "active": True, "anafData": {"cui": 12345678, "name": "ACME SRL", "inactive": False}}


def test_get_company_data_uses_fresh_cache_without_calling_anaf(monkeypatch):
    _write_cache(company.ROOT_CACHE_PATH)

    def _boom(cif):
        raise AssertionError("ANAF should not be called when a fresh cache exists")

    monkeypatch.setattr(anaf, "get_company_from_anaf", _boom)
    data = company.get_company_data()
    assert data["company"] == "CACHED SRL"
    assert data["cif"] == "12345678"


def test_get_company_data_ignores_stale_cache_and_refetches(monkeypatch):
    stale_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _write_cache(company.ROOT_CACHE_PATH, name="OLD NAME", validated_at=stale_time)
    monkeypatch.setattr(anaf, "get_company_from_anaf", lambda cif: {"cui": 12345678, "name": "FRESH NAME", "inactive": False})
    data = company.get_company_data()
    assert data["company"] == "FRESH NAME"


def test_get_company_data_falls_back_to_stale_cache_when_anaf_unreachable(monkeypatch):
    stale_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _write_cache(company.ROOT_CACHE_PATH, name="STALE BUT USABLE", validated_at=stale_time)

    def _boom(cif):
        raise RuntimeError("ANAF and CUIScan both down")

    monkeypatch.setattr(anaf, "get_company_from_anaf", _boom)
    data = company.get_company_data()
    assert data["company"] == "STALE BUT USABLE"


def test_get_company_data_falls_back_to_config_when_no_cache_and_anaf_down(monkeypatch):
    def _boom(cif):
        raise RuntimeError("ANAF and CUIScan both down")

    monkeypatch.setattr(anaf, "get_company_from_anaf", _boom)
    data = company.get_company_data()
    assert data["cif"] == str(company.COMPANY_CIF)
    assert data["company"] == company.COMPANY_LEGAL_NAME
    assert data["active"] is True
    assert data["anafData"] is None


def test_validate_and_get_company_active_saves_cache(monkeypatch, requests_mock):
    monkeypatch.setattr(anaf, "get_company_from_anaf", lambda cif: {"cui": 12345678, "name": "ACME SRL", "inactive": False, "address": "Str. X 1"})
    monkeypatch.setattr(api, "query_solr", lambda cif: {"numFound": 3, "docs": []})
    requests_mock.get(company.PEVIITOR_COMPANY_URL, json={"companies": []})

    result = company.validate_and_get_company()

    assert result["status"] == "active"
    assert result["company"] == "ACME SRL"
    assert result["address"] == "Str. X 1"
    assert company.ROOT_CACHE_PATH.exists()
    assert company.TMP_CACHE_PATH.exists()


def test_validate_and_get_company_inactive_deletes_jobs_by_cif(monkeypatch, requests_mock):
    monkeypatch.setattr(anaf, "get_company_from_anaf", lambda cif: {"cui": 12345678, "name": "DEFUNCT SRL", "inactive": True})
    monkeypatch.setattr(api, "query_solr", lambda cif: {"numFound": 5, "docs": []})
    requests_mock.get(company.PEVIITOR_COMPANY_URL, json={"companies": []})
    deleted_cifs = []
    monkeypatch.setattr(api, "delete_jobs_by_cif", lambda cif: deleted_cifs.append(cif))

    result = company.validate_and_get_company()

    assert result["status"] == "inactive"
    assert deleted_cifs == ["12345678"]


def test_validate_and_get_company_inactive_dry_run_skips_delete(monkeypatch, requests_mock):
    """Regression: dry_run used to have no path into this function at all,
    so a plain --dry-run against an ANAF-inactive company still fired a
    real, CIF-wide delete_jobs_by_cif against peviitor's live API."""
    monkeypatch.setattr(anaf, "get_company_from_anaf", lambda cif: {"cui": 12345678, "name": "DEFUNCT SRL", "inactive": True})
    monkeypatch.setattr(api, "query_solr", lambda cif: {"numFound": 5, "docs": []})
    requests_mock.get(company.PEVIITOR_COMPANY_URL, json={"companies": []})

    def _boom(cif):
        raise AssertionError("dry_run=True must never call delete_jobs_by_cif")

    monkeypatch.setattr(api, "delete_jobs_by_cif", _boom)

    result = company.validate_and_get_company(dry_run=True)
    assert result["status"] == "inactive"


def test_validate_and_get_company_inactive_skips_delete_when_solr_empty(monkeypatch, requests_mock):
    monkeypatch.setattr(anaf, "get_company_from_anaf", lambda cif: {"cui": 12345678, "name": "DEFUNCT SRL", "inactive": True})
    monkeypatch.setattr(api, "query_solr", lambda cif: {"numFound": 0, "docs": []})
    requests_mock.get(company.PEVIITOR_COMPANY_URL, json={"companies": []})

    def _boom(cif):
        raise AssertionError("should not delete when SOLR already has 0 jobs")

    monkeypatch.setattr(api, "delete_jobs_by_cif", _boom)

    result = company.validate_and_get_company()
    assert result["status"] == "inactive"


def test_validate_and_get_company_peviitor_failure_is_non_fatal(monkeypatch, requests_mock):
    monkeypatch.setattr(anaf, "get_company_from_anaf", lambda cif: {"cui": 12345678, "name": "ACME SRL", "inactive": False})
    monkeypatch.setattr(api, "query_solr", lambda cif: {"numFound": 0, "docs": []})
    requests_mock.get(company.PEVIITOR_COMPANY_URL, status_code=500)

    result = company.validate_and_get_company()
    assert result["status"] == "active"
