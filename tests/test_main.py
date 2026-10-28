"""scraper.main.run() orchestration: company validation, company upsert
(manageCompany), stale-job deletion (staleJobDeletion), and docs/ generation.

Network (ANAF, SOLR, peviitor) is always stubbed here -- these are pure
orchestration tests, not integration tests.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import pytest

from scraper import api, company as company_validation, job_validator, main
from scraper.config import company, scraper


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """Run inside a throwaway CWD, and stub every network call."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(api, "query_solr", lambda cif: {"numFound": 0, "docs": []})
    monkeypatch.setattr(api, "upsert_jobs", lambda jobs: None)
    # manageCompany and staleJobDeletion now default to True (Category 1 audit --
    # both were previously off by an unverified assumption), so every test must
    # stub these two or a bare main.run() would hit the real API.
    monkeypatch.setattr(api, "upsert_company", lambda doc: None)
    monkeypatch.setattr(api, "delete_job_by_url", lambda url: None)
    monkeypatch.setattr(
        job_validator, "validate_by_content",
        lambda url, **kw: {"url": url, "status": "active", "httpStatus": 200, "title": None, "error": None},
    )
    # ANOFM is a real network call (mediere.anofm.ro) -- stub it to empty by
    # default so every pre-existing orchestration test stays a pure unit test;
    # tests that care about ANOFM merging override this explicitly.
    monkeypatch.setattr(main, "search_anofm", lambda cif: [])
    return tmp_path


def _active(**overrides):
    base = {"status": "active", "company": "EXAMPLE CO", "cif": "12345678", "address": "Cluj-Napoca"}
    base.update(overrides)
    return base


def test_inactive_company_deletes_only_own_jobs_and_skips_scrape(monkeypatch, isolated):
    monkeypatch.setattr(
        api,
        "query_solr",
        lambda cif: {
            "numFound": 2,
            "docs": [
                {"url": f"{scraper['ownJobUrlPrefix']}ours/"},
                {"url": "https://someone-elses-board.example/jobs/theirs/"},
            ],
        },
    )
    monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active(status="inactive"))
    deleted = []
    monkeypatch.setattr(api, "delete_job_by_url", lambda url: deleted.append(url))
    scrape_called = []
    monkeypatch.setattr(main, "scrape_careers", lambda: scrape_called.append(1) or [])

    result = main.run()

    assert result == 0
    assert deleted == [f"{scraper['ownJobUrlPrefix']}ours/"]  # never touches the other scraper's job
    assert scrape_called == []  # scraping is skipped entirely


def test_manage_company_true_calls_upsert_company(monkeypatch, isolated):
    monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active())
    monkeypatch.setattr(main, "scrape_careers", lambda: [
        {"url": "https://jobs.example.com/careers/x/", "title": "X"},
    ])
    monkeypatch.setitem(scraper, "manageCompany", True)
    calls = []
    monkeypatch.setattr(api, "upsert_company", lambda doc: calls.append(doc))

    main.run()

    assert len(calls) == 1
    assert calls[0]["id"] == "12345678"
    assert calls[0]["company"] == "EXAMPLE CO"
    assert calls[0]["location"] == ["Cluj-Napoca"]
    assert calls[0]["scraperFile"] == company["scraperFile"]


def test_manage_company_false_never_calls_upsert_company(monkeypatch, isolated):
    monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active())
    monkeypatch.setattr(main, "scrape_careers", lambda: [
        {"url": "https://jobs.example.com/careers/x/", "title": "X"},
    ])
    monkeypatch.setitem(scraper, "manageCompany", False)
    called = []
    monkeypatch.setattr(api, "upsert_company", lambda doc: called.append(doc))

    main.run()

    assert called == []


def test_stale_job_deletion_true_deletes_gone_urls(monkeypatch, isolated):
    own_prefix = "https://jobs.example.com/careers/"
    monkeypatch.setattr(main, "OWN_URL_PREFIX", own_prefix)
    monkeypatch.setattr(
        api,
        "query_solr",
        lambda cif: {"numFound": 1, "docs": [{"url": f"{own_prefix}old-job/"}]},
    )
    monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active())
    monkeypatch.setattr(main, "scrape_careers", lambda: [
        {"url": f"{own_prefix}new-job/", "title": "New Job"},
    ])
    monkeypatch.setitem(scraper, "staleJobDeletion", True)
    deleted = []
    monkeypatch.setattr(api, "delete_job_by_url", lambda url: deleted.append(url))

    main.run()

    assert deleted == [f"{own_prefix}old-job/"]


def test_stale_job_deletion_false_kept_by_default(monkeypatch, isolated):
    own_prefix = "https://jobs.example.com/careers/"
    monkeypatch.setattr(main, "OWN_URL_PREFIX", own_prefix)
    monkeypatch.setattr(
        api,
        "query_solr",
        lambda cif: {"numFound": 1, "docs": [{"url": f"{own_prefix}old-job/"}]},
    )
    monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active())
    monkeypatch.setattr(main, "scrape_careers", lambda: [
        {"url": f"{own_prefix}new-job/", "title": "New Job"},
    ])
    monkeypatch.setitem(scraper, "staleJobDeletion", False)
    deleted = []
    monkeypatch.setattr(api, "delete_job_by_url", lambda url: deleted.append(url))

    main.run()

    assert deleted == []


def test_successful_run_writes_docs_jobs_md_and_company_json(monkeypatch, isolated):
    monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active())
    monkeypatch.setattr(main, "scrape_careers", lambda: [
        {"url": "https://jobs.example.com/careers/widget-engineer/", "title": "Widget Engineer"},
    ])

    main.run()

    jobs_md = Path("docs/jobs.md").read_text(encoding="utf-8")
    assert "EXAMPLE CO" in jobs_md
    assert "Widget Engineer" in jobs_md

    company_json = json.loads(Path("docs/company.json").read_text(encoding="utf-8"))
    assert "ownJobUrlPrefix" in company_json
    assert company_json["ownJobUrlPrefix"] == scraper["ownJobUrlPrefix"]


def test_summary_reflects_confirmed_post_upload_solr_state_not_local_estimate(monkeypatch, isolated, caplog):
    """The whole point of the re-query: if the real, confirmed SOLR count after
    the write differs from what we locally assumed we just upserted, the
    printed summary must show the confirmed number, not the optimistic one."""
    monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active())
    monkeypatch.setattr(main, "scrape_careers", lambda: [
        {"url": "https://jobs.example.com/careers/widget-engineer/", "title": "Widget Engineer"},
    ])
    responses = iter([
        {"numFound": 0, "docs": []},   # Step 1: nothing in SOLR yet
        {"numFound": 5, "docs": []},   # final re-query: only 5 confirmed, not the 1 we scraped
    ])
    monkeypatch.setattr(api, "query_solr", lambda cif: next(responses))

    with caplog.at_level("INFO", logger="scraper.main"):
        main.run()

    assert "jobs in SOLR after scrape:    5" in caplog.text
    with pytest.raises(StopIteration):
        next(responses)  # exactly two query_solr calls were made, no more


def test_run_sleeps_before_the_final_reverification_query(monkeypatch, isolated):
    monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active())
    monkeypatch.setattr(main, "scrape_careers", lambda: [
        {"url": "https://jobs.example.com/careers/widget-engineer/", "title": "Widget Engineer"},
    ])
    slept = []
    monkeypatch.setattr(main.time, "sleep", lambda secs: slept.append(secs))

    main.run()

    assert slept == [main._SOLR_SETTLE_DELAY_SEC]


def test_to_job_model_date_is_solr_safe_not_pythons_native_isoformat():
    """peviitor's Solr date field parses only "...SSSZ" (JS's toISOString()
    shape). Python's bare datetime.isoformat() instead emits microseconds and
    a "+00:00" offset, which Solr's date field rejects with a 400 -- this is
    what an unpadded 18-job upload from this scraper actually hit."""
    job = main._to_job_model({"url": "https://x/y/", "title": "T"}, "12345678", "EXAMPLE CO")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", job["date"])


class _FakeResp:
    def __init__(self, text=""):
        self.text = text

    def raise_for_status(self):
        pass


class TestScrapeCareersUrlSelection:
    """A real permalink whose ID a title-slug guess could never reproduce
    (e.g. "/jobs/jr133930/software-architect-fanduel-hybrid/") is exactly
    what silently reached peviitor as a 404 before parse_listing scraped
    real hrefs. The real URL must now win whenever it's present."""

    def test_prefers_the_real_scraped_url_over_a_guessed_slug(self, monkeypatch, isolated):
        monkeypatch.setattr(main.fetch, "get", lambda url, **kw: _FakeResp())
        monkeypatch.setattr(main, "parse_listing", lambda html: [
            {
                "title": "Software Architect - FanDuel, Hybrid",
                "expirationdate": None,
                "url": "/jobs/jr133930/software-architect-fanduel-hybrid/",
            },
        ])

        jobs = main.scrape_careers()

        assert jobs[0]["url"] == urljoin(
            scraper["sources"]["listing"], "/jobs/jr133930/software-architect-fanduel-hybrid/"
        )

    def test_falls_back_to_a_guessed_slug_when_nothing_was_scraped(self, monkeypatch, isolated):
        monkeypatch.setattr(main.fetch, "get", lambda url, **kw: _FakeResp())
        monkeypatch.setattr(main, "parse_listing", lambda html: [
            {"title": "Some Job", "expirationdate": None, "url": None},
        ])

        jobs = main.scrape_careers()

        assert jobs[0]["url"] == f'{scraper["sources"]["jobArchive"]}some-job/'

    def test_exact_sitemap_match_wins_over_an_earlier_fuzzy_match(self, monkeypatch, isolated):
        """Regression for a real Antibiotice scrape: the sitemap only lists
        "reprezentant-medical", but the listing page also carries a second,
        genuinely different, unlinked posting whose slug happens to extend
        that one ("reprezentant-medical-si-vanzari-veterinare"). Neither
        article has an <a href>, so both fall to sitemap matching -- and the
        longer title's slug is a bounded-prefix ("fuzzy") match for the
        shorter one's exact sitemap entry. If that fuzzy match wins just
        because its item is scraped first, the real "Reprezentant Medical"
        posting is left without its own real URL and both jobs collapse onto
        one SOLR document. An exact match must win the slot regardless of
        item order, and the fuzzy-matched title must fall through to a
        guessed (and here, 404ing) slug instead of stealing it."""
        monkeypatch.setattr(main.fetch, "get", lambda url, **kw: _FakeResp())
        monkeypatch.setattr(main, "parse_listing", lambda html: [
            # Deliberately listed BEFORE its exact-match counterpart, since the
            # bug only reproduces when the fuzzy-matching title is scraped first.
            {"title": "Reprezentant Medical si Vanzari - Veterinare", "expirationdate": None, "url": None},
            {"title": "Reprezentant Medical", "expirationdate": None, "url": None},
        ])
        monkeypatch.setattr(main, "fetch_sitemap_job_urls", lambda: [
            {"url": "https://jobs.example.com/careers/reprezentant-medical/", "slug": "reprezentant-medical"},
        ])

        jobs = main.scrape_careers()

        urls = [j["url"] for j in jobs]
        assert len(urls) == len(set(urls)), "two distinct postings must never share one URL"
        assert jobs[1]["url"] == "https://jobs.example.com/careers/reprezentant-medical/"
        assert jobs[0]["url"] == f'{scraper["sources"]["jobArchive"]}reprezentant-medical-si-vanzari-veterinare/'


class TestSearchAnofm:
    """Parity fix: the JS template always searched ANOFM by CIF as a
    supplementary source in addition to the company's own careers site; the
    Python template shipped without it since it was first written."""

    def test_maps_anofm_rows_into_job_dicts(self, monkeypatch):
        monkeypatch.setattr(main.fetch, "post", lambda url, **kw: _FakeJsonResp({
            "rows": [
                {"id": 123, "occupation": "Sudor", "address_locality_name": "Judet > Oras > Sat"},
                {"id": 456, "occupation": "Electrician", "address_locality_name": "Bistrita"},
            ]
        }))

        jobs = main.search_anofm("12345678")

        assert jobs == [
            {
                "url": "https://mediere.anofm.ro/app/module/mediere/job/123",
                "title": "Sudor",
                "location": ["Sat"],
                "source": "ANOFM",
            },
            {
                "url": "https://mediere.anofm.ro/app/module/mediere/job/456",
                "title": "Electrician",
                "location": ["Bistrita"],
                "source": "ANOFM",
            },
        ]

    def test_returns_empty_list_on_non_ok_response(self, monkeypatch):
        monkeypatch.setattr(main.fetch, "post", lambda url, **kw: _FakeJsonResp({}, ok=False))
        assert main.search_anofm("12345678") == []

    def test_returns_empty_list_and_does_not_raise_on_network_error(self, monkeypatch):
        def boom(url, **kw):
            raise ConnectionError("boom")

        monkeypatch.setattr(main.fetch, "post", boom)
        assert main.search_anofm("12345678") == []

    def test_skips_rows_missing_id_or_occupation(self, monkeypatch):
        monkeypatch.setattr(main.fetch, "post", lambda url, **kw: _FakeJsonResp({
            "rows": [{"id": None, "occupation": "X"}, {"id": 1, "occupation": None}]
        }))
        assert main.search_anofm("12345678") == []

    def test_run_merges_anofm_jobs_alongside_careers_site_jobs(self, monkeypatch, isolated):
        monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active())
        monkeypatch.setattr(main, "scrape_careers", lambda: [
            {"url": "https://jobs.example.com/careers/x/", "title": "X"},
        ])
        monkeypatch.setattr(main, "search_anofm", lambda cif: [
            {"url": "https://mediere.anofm.ro/app/module/mediere/job/1", "title": "Y", "source": "ANOFM"},
        ])
        upserted = []
        monkeypatch.setattr(api, "upsert_jobs", lambda jobs: upserted.append(jobs))

        main.run()

        urls = {j["url"] for j in upserted[0]}
        assert urls == {"https://jobs.example.com/careers/x/", "https://mediere.anofm.ro/app/module/mediere/job/1"}

    def test_run_does_not_duplicate_a_url_present_in_both_sources(self, monkeypatch, isolated):
        shared_url = "https://jobs.example.com/careers/x/"
        monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active())
        monkeypatch.setattr(main, "scrape_careers", lambda: [{"url": shared_url, "title": "X"}])
        monkeypatch.setattr(main, "search_anofm", lambda cif: [
            {"url": shared_url, "title": "X (ANOFM copy)", "source": "ANOFM"},
        ])
        upserted = []
        monkeypatch.setattr(api, "upsert_jobs", lambda jobs: upserted.append(jobs))

        main.run()

        assert len(upserted[0]) == 1


class _FakeJsonResp:
    def __init__(self, data, ok=True):
        self._data = data
        self.ok = ok
        self.status_code = 200 if ok else 500

    def json(self):
        return self._data


class TestDropDeadUrls:
    def test_keeps_active_and_drops_expired_or_erroring(self, monkeypatch):
        def fake_content_check(url, **kw):
            status = "active" if "good" in url else "expired"
            return {"url": url, "status": status, "httpStatus": 200 if status == "active" else 404, "title": None, "error": None}

        monkeypatch.setattr(job_validator, "validate_by_content", fake_content_check)

        jobs = [
            {"url": "https://x/good/", "title": "Good"},
            {"url": "https://x/bad/", "title": "Bad"},
        ]
        kept = main._drop_dead_urls(jobs)

        assert [j["title"] for j in kept] == ["Good"]

    def test_run_skips_upsert_when_every_job_fails_live_validation(self, monkeypatch, isolated):
        """404s must never reach peviitor -- and an empty array must never
        be sent to api.upsert_jobs (the API rejects it)."""
        monkeypatch.setattr(company_validation, "validate_and_get_company", lambda **kw: _active())
        monkeypatch.setattr(main, "scrape_careers", lambda: [
            {"url": "https://jobs.example.com/careers/widget-engineer/", "title": "Widget Engineer"},
        ])
        monkeypatch.setattr(
            job_validator, "validate_by_content",
            lambda url, **kw: {"url": url, "status": "expired", "httpStatus": 404, "title": None, "error": None},
        )
        calls = []
        monkeypatch.setattr(api, "upsert_jobs", lambda jobs: calls.append(jobs))

        count = main.run()

        assert count == 0
        assert calls == []
