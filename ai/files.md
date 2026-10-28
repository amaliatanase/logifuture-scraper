# Project Files

## Python Files — scraper/

| File | Description |
|------|--------------|
| `scraper/main.py` | Main scraper — full workflow: validate company → scrape → transform → upsert → generate docs. Source-specific: `scrape_careers`, `fetch_sitemap_job_urls`, `_match_sitemap_url` |
| `scraper/company.py` | Validates company via ANAF + CUIScan + Peviitor APIs, checks if company is active/inactive, caches to `company.json` / `tmp/company.json` |
| `scraper/anaf.py` | Multi-source company data module — ANAF + CUIScan (company details) + CUIFirma (search). Exports `get_company_from_anaf`, `get_company_from_anaf_with_fallback`, `search_company` |
| `scraper/api.py` | Peviitor API operations module — exports `query_solr`, `upsert_jobs`, `delete_job_by_url`, `delete_jobs_by_cif`, `upsert_company` |
| `scraper/validate_jobs.py` | **Generic deep validator (manual use).** Full GET requests, parses page body for "no longer available" keywords. Works with any CIF, single URL, or file. Slower but catches soft-404s. Not used by default CI. |
| `scraper/job_validator.py` | Shared validation primitives — `validate_by_head(url)`, `validate_by_content(url, **opts)`, `validate_by_browser(url, **opts)`, `DEFAULT_EXPIRED_KEYWORDS`. `validate_by_browser` needs the optional `browser` extra (Playwright); falls back to `validate_by_content` otherwise. |
| `scraper/self_healing.py` | **Generic** selector cascade — `first_match`, `locate_articles`, `json_ld_job_postings`, `css_text`/`structural_text`/`regex_text`. Primary CSS → fallback CSS → structural/JSON-LD → regex, one `try/except` + log per strategy. Consumed by `parse.py`. See `ai/AGENTS.md`. |
| `scraper/validate.py` | **Generic** pre-publish data validation — `validate_job` (url/title/location/salary), `filter_valid_jobs` (drops + logs), `assert_scrape_yielded_jobs` (the 0-result canary). |
| `scraper/markdown_generator.py` | Generates `docs/jobs.md` — exports `generate_jobs_markdown(company_data, jobs)` |
| `scraper/parse.py` | Site-specific listing parser (`parse_listing`), driven by the self-healing cascade and `config/scraper.json`'s selectors |
| `scraper/fetch.py` | HTTP with retry + full-jitter exponential backoff |
| `scraper/config.py` | Loads `config/company.json` + `config/scraper.json` |

## Config — config/

| File | Description |
|------|--------------|
| `config/company.json` | **Single source of truth for company identity.** All scraper code, CI workflows, and the static HTML read from this file. To derive a scraper for a different company, this is the primary file to edit. `scraperFile` must be the GitHub Actions workflow URL (not raw). |
| `config/scraper.json` | Source config: careers-site sitemap/listing/jobArchive URLs, CSS selector cascades, delays, timeouts, `ownJobUrlPrefix`, `defaultLocation`, `defaultWorkmode`, `staleJobDeletion`, `manageCompany` |

## Test Files — tests/

| File | Description |
|------|--------------|
| `tests/conftest.py` | Shared fixtures — example selector cascade, fixture-HTML loader |
| `tests/fixtures/*.html` | Listing-page fixtures for the self-healing cascade tests |
| `tests/test_fetch_retry.py` | Unit tests for `fetch.py` — retry/backoff behaviour |
| `tests/test_self_healing.py` | Unit tests for `self_healing.py` — each cascade level in isolation, all-fail logging, JSON-LD, `locate_articles` modes |
| `tests/test_parse.py` | Unit tests for `parse.py` — `parse_listing`, `parse_deadline`, `slugify` |
| `tests/test_validate.py` | Unit tests for `validate.py` — url/title/location/salary rules, `filter_valid_jobs`, the canary |
| `tests/test_main_canary.py` | The 0-result canary must stop `main.run()` before any API write |
| `tests/test_main.py` | Orchestration tests — company validation, `manageCompany`, `staleJobDeletion`, docs generation |
| `tests/test_anaf.py` | Unit tests for `anaf.py` — ANAF/CUIScan/CUIFirma fallback chains |
| `tests/test_company.py` | Unit tests for `company.py` — cache freshness, ANAF fallback, inactive-company cleanup |
| `tests/test_api.py` | Unit tests for `api.py` — query, upsert, delete, HTTP error handling |
| `tests/test_markdown_generator.py` | Unit tests for `markdown_generator.py` |
| `tests/test_job_validator.py` | Unit tests for `job_validator.py` — head/content/browser validation |
| `tests/test_validate_jobs.py` | Unit tests for the `validate_jobs.py` CLI |
| `tests/integration/test_company_real.py` | Live integration tests — ANAF/CUIScan + Peviitor API (self-skips until derived / unreachable) |
| `tests/e2e/test_scraper.py` | End-to-end test against the real careers site (self-skips until derived / unreachable) |
| `tests/consistency/test_repo.py` | Verifies required root files, ai/ docs, workflow files, changelog, .gitignore |
| `tests/consistency/test_readme.py` | Verifies README.md structure |
| `tests/consistency/test_code_of_conduct.py` | Verifies CODE_OF_CONDUCT.md stays a full Contributor Covenant document |

## Markdown Files

| File | Description |
|------|--------------|
| `INSTRUCTIONS.md` | Project documentation — workflow, technologies, API endpoints, how to update models |
| `JOB_MODEL.md` | Job schema definition (Peviitor Core) — fields, types, validation rules |
| `COMPANY_MODEL.md` | Company schema definition (Peviitor Core) — fields, types, validation rules |
| `files.md` | This file — documents the role of each project file |
| `AGENTS.md` | Rules for AI agents working on this project |
| `BRANCH.md` | Branch strategy and naming conventions |
| `SELF-HEALING.md` | JS↔Python parity notes for the self-healing cascade + the optional Scrapling adaptive layer |
| `ISSUES.md` | Issue tracking conventions |
| `PUBLIC.md` | Notes on public visibility and data policies |
| `ROBOTS.md` | robots.txt analysis and scraping policy for the careers site |
| `TOPICS.md` | Repository topics documentation |
| `UPDATE-REPO-ABOUT.md` | Instructions for updating repo description/about |
| `VERIFY.md` | Step-by-step verification checklist after changes |

## Configuration Files

| File | Description |
|------|--------------|
| `pyproject.toml` | Python project config — dependencies, optional extras (`adaptive`, `browser`, `dev`), pytest config |
| `requirements.txt` | Pinned runtime dependencies |
| `.gitignore` | Ignores `__pycache__/`, `.venv/`, `tmp/`, `.env.local` |
| `.env.local` | Local environment variables — NOT committed |
| `CHANGELOG.md` | Version history and notable changes |
| `CONTRIBUTING.md` | Contribution guidelines |
| `.github/workflows/scrape.yml` | Daily scraping workflow (cron + dispatch) |
| `.github/workflows/tests.yml` | Automated tests on every push/PR |
| `.github/workflows/job-deep-validate.yml` | Manual deep validation (content mode — GET + body scan) |
| `.github/workflows/automation-template-sync-check.yml` | Weekly check that derived scrapers are up to date with this template |
| `.github/workflows/job-recovery-from-disaster.yml` | Manual: restores the company core entry from `config/company.json` |
| `CODE_OF_CONDUCT.md` | Community code of conduct (Contributor Covenant 2.0) |
| `SECURITY.md` | Security policy and vulnerability reporting |

## Data Files

| File | Description |
|------|--------------|
| `tmp/company.json` | **Per-run scratch cache (gitignored).** Survives between CI runs so the scraper does not hit ANAF on every scrape. Refreshed when older than 7 days. |
| `company.json` (root) | **Committed cache.** Refreshed every 7 days. If ANAF is unreachable AND the cache is stale, falls back to the stale cache rather than failing. |
| `docs/company.json` | Static copy of `config/company.json` regenerated on each scrape. Served by GitHub Pages so the live page can read company identity without hardcoding it in HTML. |
| `docs/jobs.md` | Scraped jobs in markdown format — company info + all current jobs (generated by CI after each scrape) |

## Notes

- All `.md` schema files (`JOB_MODEL.md`, `COMPANY_MODEL.md`) are dynamic — check peviitor_core's README.md for updates
- `tmp/` directory holds runtime artifacts — not committed
- Full workflow: validate company (ANAF+CUIScan+Peviitor) → scrape the careers site → transform → upsert → generate docs
