"""scraper.api -- the peviitor v1 API client (query/upsert/delete)."""

import json

import pytest

from scraper import api


def test_pad_cif_zero_pads_to_eight_digits():
    assert api.pad_cif("123") == "00000123"
    assert api.pad_cif(12345678) == "12345678"


def test_query_solr(requests_mock):
    requests_mock.get(
        f"{api.API_BASE}/scraper/jobs/?cif=12345678&rows=500",
        json={"total": 2, "data": [{"url": "a"}, {"url": "b"}]},
    )
    result = api.query_solr("12345678")
    assert result == {"numFound": 2, "docs": [{"url": "a"}, {"url": "b"}]}


def test_upsert_jobs_pads_cif_in_payload(requests_mock):
    m = requests_mock.post(f"{api.API_BASE}/scraper/jobs/upload/", json={"count": 1})
    api.upsert_jobs([{"cif": "123", "title": "X"}])
    sent = json.loads(m.last_request.body)
    assert sent[0]["cif"] == "00000123"


def test_delete_job_by_url_treats_404_as_success(requests_mock):
    requests_mock.delete(f"{api.API_BASE}/scraper/jobs/delete/", status_code=404)
    api.delete_job_by_url("https://example.com/jobs/gone/")  # must not raise


def test_delete_job_by_url_raises_on_error(requests_mock):
    requests_mock.delete(f"{api.API_BASE}/scraper/jobs/delete/", status_code=500, text="boom")
    with pytest.raises(RuntimeError):
        api.delete_job_by_url("https://example.com/jobs/x/")


def test_delete_jobs_by_cif_pads_cif(requests_mock):
    m = requests_mock.delete(f"{api.API_BASE}/cleanjobs/", json={"success": True})
    api.delete_jobs_by_cif("123")
    sent = json.loads(m.last_request.body)
    assert sent["cif"] == "00000123"


def test_delete_jobs_by_cif_treats_404_as_success(requests_mock):
    requests_mock.delete(f"{api.API_BASE}/cleanjobs/", status_code=404)
    api.delete_jobs_by_cif("12345678")  # must not raise


def test_upsert_company_pads_id_and_requires_success_flag(requests_mock):
    m = requests_mock.put(f"{api.API_BASE}/firme/company/add/", json={"success": True})
    api.upsert_company({"id": "123", "company": "ACME SRL"})
    sent = json.loads(m.last_request.body)
    assert sent["id"] == "00000123"
    assert sent["company"] == "ACME SRL"


def test_upsert_company_raises_when_api_reports_failure(requests_mock):
    requests_mock.put(f"{api.API_BASE}/firme/company/add/", json={"success": False, "error": "bad doc"})
    with pytest.raises(RuntimeError):
        api.upsert_company({"id": "12345678", "company": "ACME SRL"})


def test_upsert_company_raises_on_http_error(requests_mock):
    requests_mock.put(f"{api.API_BASE}/firme/company/add/", status_code=500, text="boom")
    with pytest.raises(RuntimeError):
        api.upsert_company({"id": "12345678", "company": "ACME SRL"})
