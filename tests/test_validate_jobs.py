"""scraper.validate_jobs -- the manual deep-validation CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scraper import api, validate_jobs as vj


@pytest.fixture(autouse=True)
def isolated_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


def _fake_validate_by_content(results_by_url):
    def _run(url, **kwargs):
        return results_by_url[url]

    return _run


def test_check_urls_classifies_by_status(monkeypatch):
    monkeypatch.setattr(
        vj,
        "validate_by_content",
        _fake_validate_by_content({
            "a": {"url": "a", "status": "active", "httpStatus": 200, "title": "A", "error": None},
            "b": {"url": "b", "status": "expired", "httpStatus": 200, "title": None, "error": None},
            "c": {"url": "c", "status": "error", "httpStatus": 0, "title": None, "error": "boom"},
        }),
    )
    results = vj.check_urls(["a", "b", "c"])
    assert [r["url"] for r in results["active"]] == ["a"]
    assert [r["url"] for r in results["expired"]] == ["b"]
    assert [r["url"] for r in results["error"]] == ["c"]


def test_load_urls_from_file_array_of_strings(tmp_path):
    f = tmp_path / "jobs.json"
    f.write_text(json.dumps(["https://x/1/", "https://x/2/"]))
    assert vj.load_urls_from_file(str(f)) == ["https://x/1/", "https://x/2/"]


def test_load_urls_from_file_jobs_wrapper(tmp_path):
    f = tmp_path / "jobs.json"
    f.write_text(json.dumps({"jobs": [{"url": "https://x/1/"}, "https://x/2/"]}))
    assert vj.load_urls_from_file(str(f)) == ["https://x/1/", "https://x/2/"]


def test_load_urls_from_file_urls_wrapper(tmp_path):
    f = tmp_path / "jobs.json"
    f.write_text(json.dumps({"urls": ["https://x/1/"]}))
    assert vj.load_urls_from_file(str(f)) == ["https://x/1/"]


def test_load_urls_from_file_unknown_format_raises(tmp_path):
    f = tmp_path / "jobs.json"
    f.write_text(json.dumps({"nope": []}))
    with pytest.raises(ValueError):
        vj.load_urls_from_file(str(f))


def test_delete_expired_jobs_calls_api_delete(monkeypatch):
    deleted = []
    monkeypatch.setattr(api, "delete_job_by_url", lambda url: deleted.append(url))
    own1, own2 = f"{vj.OWN_URL_PREFIX}1/", f"{vj.OWN_URL_PREFIX}2/"
    vj.delete_expired_jobs([{"url": own1}, {"url": own2}])
    assert deleted == [own1, own2]


def test_delete_expired_jobs_skips_urls_not_owned_by_this_scraper(monkeypatch):
    # Regression: the same CIF can carry jobs from another peviitor scraper
    # or aggregator (eJobs, BestJobs imports, etc.); query_solr(cif) returns
    # all of them undifferentiated, so delete_expired_jobs must never delete
    # one just because it failed THIS scraper's live-URL check.
    deleted = []
    monkeypatch.setattr(api, "delete_job_by_url", lambda url: deleted.append(url))
    own = f"{vj.OWN_URL_PREFIX}1/"
    vj.delete_expired_jobs([{"url": own}, {"url": "https://someone-elses-board.example/jobs/theirs/"}])
    assert deleted == [own]


def test_main_cif_mode_without_delete_writes_expired_jobs_file(monkeypatch):
    own = f"{vj.OWN_URL_PREFIX}1/"
    monkeypatch.setattr(api, "query_solr", lambda cif: {"numFound": 1, "docs": [{"url": own}]})
    monkeypatch.setattr(
        vj,
        "validate_by_content",
        _fake_validate_by_content({own: {"url": own, "status": "expired", "httpStatus": 404, "title": None, "error": None}}),
    )
    exit_code = vj.main(["12345678"])
    assert exit_code == 0
    output = json.loads(Path("tmp/expired-jobs.json").read_text(encoding="utf-8"))
    assert output["summary"]["expired"] == 1


def test_main_cif_mode_with_delete_flag_deletes(monkeypatch):
    own = f"{vj.OWN_URL_PREFIX}1/"
    monkeypatch.setattr(api, "query_solr", lambda cif: {"numFound": 1, "docs": [{"url": own}]})
    monkeypatch.setattr(
        vj,
        "validate_by_content",
        _fake_validate_by_content({own: {"url": own, "status": "expired", "httpStatus": 404, "title": None, "error": None}}),
    )
    deleted = []
    monkeypatch.setattr(api, "delete_job_by_url", lambda url: deleted.append(url))
    vj.main(["12345678", "--delete"])
    assert deleted == [own]


def test_main_url_mode(monkeypatch):
    monkeypatch.setattr(
        vj,
        "validate_by_content",
        _fake_validate_by_content({"https://x/1/": {"url": "https://x/1/", "status": "active", "httpStatus": 200, "title": None, "error": None}}),
    )
    assert vj.main(["--url", "https://x/1/"]) == 0


def test_main_no_args_shows_help_and_exits_nonzero():
    assert vj.main([]) == 1
