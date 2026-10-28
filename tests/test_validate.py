import logging

import pytest

from scraper.validate import (
    CanaryError,
    assert_scrape_yielded_jobs,
    filter_valid_jobs,
    validate_job,
)

GOOD = {
    "url": "https://jobs.example.com/careers/widget-engineer/",
    "title": "Widget Engineer",
    "location": ["Iași"],
}


class TestValidateJob:
    def test_accepts_a_clean_job(self):
        assert validate_job(GOOD) == (True, [])

    @pytest.mark.parametrize("bad_url, needle", [
        ("", "url is empty"),
        ("not a url", "not a valid URL"),
        ("ftp://example.com/j", "non-http"),
    ])
    def test_bad_url(self, bad_url, needle):
        ok, errors = validate_job({**GOOD, "url": bad_url})
        assert not ok
        assert any(needle in e for e in errors)

    def test_empty_title(self):
        assert "title is empty" in validate_job({**GOOD, "title": "   "})[1]

    def test_title_with_html(self):
        assert "title contains HTML" in validate_job({**GOOD, "title": "Dev <script>x</script>"})[1]

    def test_title_too_long(self):
        ok, errors = validate_job({**GOOD, "title": "x" * 201})
        assert not ok and any("exceeds 200" in e for e in errors)

    def test_location_must_be_list_of_non_empty_strings(self):
        assert "location is not a list" in validate_job({**GOOD, "location": "Iași"})[1]
        assert "location has an empty entry" in validate_job({**GOOD, "location": ["Iași", ""]})[1]

    def test_salary_rules(self):
        assert validate_job({**GOOD, "salary": "5000-8000 RON"})[0] is True   # range, not negative
        assert any("negative" in e for e in validate_job({**GOOD, "salary": "-2000 RON"})[1])
        assert "salary is not a string" in validate_job({**GOOD, "salary": 5000})[1]

    def test_reports_multiple_errors(self):
        ok, errors = validate_job({"url": "bad", "title": ""})
        assert not ok and len(errors) >= 2

    def test_non_dict(self):
        assert validate_job(None) == (False, ["job is not a dict"])


class TestFilterValidJobs:
    def test_keeps_good_drops_bad_and_logs(self, caplog):
        jobs = [GOOD, {"url": "https://x.ro/a", "title": ""}, {"url": "nonsense", "title": "T"}]
        with caplog.at_level(logging.WARNING):
            kept, dropped = filter_valid_jobs(jobs)
        assert kept == [GOOD]
        assert len(dropped) == 2
        assert "2/3 job(s) failed validation" in caplog.text

    def test_all_valid_logs_nothing(self, caplog):
        with caplog.at_level(logging.WARNING):
            kept, dropped = filter_valid_jobs([GOOD, {**GOOD, "url": "https://x.ro/b"}])
        assert len(kept) == 2 and dropped == []
        assert caplog.text == ""


class TestCanary:
    def test_raises_on_empty(self):
        with pytest.raises(CanaryError, match="0 jobs"):
            assert_scrape_yielded_jobs([])
        with pytest.raises(CanaryError):
            assert_scrape_yielded_jobs(0)

    def test_returns_count_when_present(self):
        assert assert_scrape_yielded_jobs([{}, {}, {}]) == 3
        assert assert_scrape_yielded_jobs(5) == 5
