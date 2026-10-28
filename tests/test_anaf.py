"""ANAF (demoanaf.ro) -> CUIScan -> caller's cache fallback chain."""

import pytest
import requests

from scraper import anaf


def test_get_company_from_anaf_uses_demoanaf_when_it_succeeds(requests_mock):
    requests_mock.get(f"{anaf.ANAF_API_URL}12345678", json={"success": True, "data": {"name": "ACME SRL", "cui": 12345678}})
    data = anaf.get_company_from_anaf("12345678")
    assert data == {"name": "ACME SRL", "cui": 12345678}


def test_get_company_from_anaf_falls_back_to_cuiscan_on_demoanaf_failure(requests_mock):
    requests_mock.get(f"{anaf.ANAF_API_URL}12345678", status_code=500)
    requests_mock.get(
        anaf.CUISCAN_API_URL,
        json={"denumire": "ACME SRL", "cui": "12345678", "activ": True, "adresa": "Str. Exemplu 1"},
    )
    data = anaf.get_company_from_anaf("12345678")
    assert data["name"] == "ACME SRL"
    assert data["inactive"] is False
    assert data["address"] == "Str. Exemplu 1"


def test_get_company_from_anaf_raises_when_both_sources_fail(requests_mock):
    requests_mock.get(f"{anaf.ANAF_API_URL}12345678", status_code=500)
    requests_mock.get(anaf.CUISCAN_API_URL, status_code=500)
    with pytest.raises(Exception):
        anaf.get_company_from_anaf("12345678")


def test_get_company_from_anaf_with_fallback_uses_cache_when_both_sources_fail(requests_mock):
    requests_mock.get(f"{anaf.ANAF_API_URL}12345678", status_code=500)
    requests_mock.get(anaf.CUISCAN_API_URL, status_code=500)
    cached = {"name": "CACHED SRL", "cui": 12345678}
    data = anaf.get_company_from_anaf_with_fallback("12345678", cached_data=cached)
    assert data == cached


def test_get_company_from_anaf_with_fallback_reraises_when_no_cache(requests_mock):
    requests_mock.get(f"{anaf.ANAF_API_URL}12345678", status_code=500)
    requests_mock.get(anaf.CUISCAN_API_URL, status_code=500)
    with pytest.raises(Exception):
        anaf.get_company_from_anaf_with_fallback("12345678", cached_data=None)


def test_search_company_uses_demoanaf_search_first(requests_mock):
    requests_mock.get(anaf.ANAF_SEARCH_URL, json={"data": [{"cui": "1", "name": "ACME"}]})
    results = anaf.search_company("ACME")
    assert results == [{"cui": "1", "name": "ACME"}]


def test_search_company_falls_back_to_cuifirma(requests_mock):
    requests_mock.get(anaf.ANAF_SEARCH_URL, status_code=500)
    requests_mock.get(
        anaf.CUIFIRMA_SEARCH_URL,
        json={"results": [{"cui": 1, "name": "ACME", "is_active": True}]},
    )
    results = anaf.search_company("ACME")
    assert results == [{"cui": "1", "name": "ACME", "statusLabel": "Funcțiune"}]


def test_anaf_calls_are_single_attempt_no_retry(requests_mock):
    # A connection error on demoanaf must fall straight to cuiscan without
    # scraper.fetch's retry/backoff wrapper kicking in (anaf.py bypasses it).
    requests_mock.get(f"{anaf.ANAF_API_URL}1", exc=requests.ConnectionError("boom"))
    requests_mock.get(anaf.CUISCAN_API_URL, json={"denumire": "X", "cui": "1", "activ": True})
    anaf.get_company_from_anaf("1")
    demoanaf_calls = [r for r in requests_mock.request_history if "demoanaf" in r.url]
    assert len(demoanaf_calls) == 1
