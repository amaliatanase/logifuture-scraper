"""scraper.markdown_generator -- docs/jobs.md rendering."""

from scraper.markdown_generator import generate_jobs_markdown


def test_renders_company_table_and_job_sections():
    company_data = {
        "id": "12345678",
        "company": "ACME SRL",
        "brand": "Acme",
        "status": "activ",
        "location": ["Cluj-Napoca"],
        "website": ["https://acme.ro"],
        "career": ["https://acme.ro/cariere"],
        "lastScraped": "2026-01-01",
    }
    jobs = [
        {"url": "https://acme.ro/jobs/dev/", "title": "Developer", "workmode": "hybrid", "location": ["Cluj-Napoca"], "status": "scraped"},
        {"url": "https://acme.ro/jobs/qa/", "title": "QA Engineer"},
    ]

    md = generate_jobs_markdown(company_data, jobs)

    assert md.startswith("# ACME SRL")
    assert "| CIF | 12345678 |" in md
    assert "| Brand | Acme |" in md
    assert "## Current Job Listings (2)" in md
    assert "### Developer" in md
    assert "[https://acme.ro/jobs/dev/](https://acme.ro/jobs/dev/)" in md
    assert "**Work Mode:** hybrid" in md
    assert "### QA Engineer" in md


def test_escapes_markdown_special_characters_in_title():
    company_data = {"id": "1", "company": "ACME"}
    jobs = [{"url": "https://x", "title": "Senior *Engineer* [Backend]"}]
    md = generate_jobs_markdown(company_data, jobs)
    assert r"Senior \*Engineer\* \[Backend\]" in md


def test_empty_jobs_list_still_renders_company_section():
    md = generate_jobs_markdown({"id": "1", "company": "ACME"}, [])
    assert "## Current Job Listings (0)" in md
