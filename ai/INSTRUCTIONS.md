# Instructions

## Project Purpose

This scraper extracts job listings for **LOGIFUTURE** (CIF: 49014718) from
the company's own careers site, validates the company via ANAF, and imports
the jobs to peviitor.ro.

Targets: https://apply.workable.com/logifuture/, 

## Model Schemas

The job and company models are defined in:
- `JOB_MODEL.md` — job model schema
- `COMPANY_MODEL.md` — company model schema

## Important

These models are **dynamic** and can change over time. They are based on the
official Peviitor Core schemas which may be updated.

## How to Keep Models Updated

When working on this scraper:

1. **Check for updates** in the Peviitor Core repository:
   - Repository: https://github.com/peviitor-ro/peviitor_core
   - Main file: README.md (contains Job and Company model schemas)

2. **When to update**:
   - Before starting new development work
   - If field requirements or validations have changed
   - If new fields have been added

3. **How to update**:
   - Fetch the latest README.md from peviitor_core main branch
   - Compare with current `JOB_MODEL.md` and `COMPANY_MODEL.md`
   - Update local files if there are differences
   - Update `scraper/main.py`'s mapping logic if field requirements changed

## Technologies

- **Python** — for scraping and data extraction
- **Peviitor API** — for data storage and retrieval (api.peviitor.ro)
- **Claude Code** — for development

## Workflow Steps

1. **Start with brand** — we know the brand (from `config/company.json`)
2. **Get company details from ANAF** — using the configured CIF, fetch full
   company data (`scraper/anaf.py`: demoanaf.ro → cuiscan.ro fallback)
3. **Validate with Peviitor** — verify company exists in peviitor, get
   group/brand info (`scraper/company.py`)
4. **Check existing jobs** — query peviitor API by CIF to see what jobs
   already exist
5. **Check company status** — if ANAF status is inactive → delete our own
   jobs and stop
6. **Save company cache** — save ANAF + peviitor data for backup
   (`company.json` / `tmp/company.json`, 7-day TTL)
7. **Scrape new jobs** — parse the careers page (`requests` + BeautifulSoup),
   reconcile titles against the job sitemap
8. **Transform for API** — validate and fix job data:
   - location: only Romanian cities allowed
   - company: uppercase
9. **Upsert to API** — import/update jobs via peviitor API
10. **Generate docs** — write `docs/jobs.md` + `docs/company.json` for
    GitHub Pages
11. **Verify URLs** — check existing job URLs still work, delete 404s
    (`scraper/validate_jobs.py`, run manually or via `job-deep-validate.yml`)

## Running the Scraper

```bash
# Run the full scraper workflow (single command)
python -m scraper.main

# Dry run — scrape and validate, but do not write to the API
python -m scraper.main --dry-run
```

> **Important**: if the CIF is shared with another peviitor scraper, this
> scraper only upserts jobs it scraped from the careers site and only ever
> touches URLs under its own `ownJobUrlPrefix`. Jobs from other scrapers are
> preserved. Stale-job deletion is disabled by default (`staleJobDeletion: false`).

## Full Workflow (automatic)

When running `python -m scraper.main`, the following steps happen automatically:

1. **Check existing jobs count** — query peviitor API by CIF (read-only); note which URLs are ours
2. **Validate company via ANAF** — check company exists and is active
3. **Scrape jobs** — parse the careers page + job sitemap
4. **Transform for API** — fix locations (only Romanian cities), normalize fields
5. **Upsert to API** — add/update jobs (API handles duplicates by URL)
6. **Generate docs** — write `docs/jobs.md` + `docs/company.json`
7. **Delete stale jobs** — disabled by default (`staleJobDeletion: false`); the
   deep-validate workflow handles real 404s
8. **Show Summary** — log job counts

## Workflow Flowchart

```
config/company.json  + config/scraper.json (sources, selectors)
    │
    ▼
scraper/main.py
    │
    ▼
query_solr(CIF) - check existing jobs (note our own URLs)
    │
    ▼
scraper/company.py (validate company)
    ├── load cache (tmp/company.json, then company.json)
    │   └── if fresh (<7 days), skip ANAF entirely
    ├── ANAF API (demoanaf.ro) ──► get company name + CIF
    ├── CUIScan ──► fallback if ANAF fails
    ├── Peviitor API ──► validate company model
    └── SOLR ──► check existing jobs count
    │
    ▼ (if active)
scrape_careers()
    ├── fetch_sitemap_job_urls()  (job sitemap → canonical permalinks)
    ├── fetch listing + parse_listing()  (self-healing cascade, see AGENTS.md)
    └── match_sitemap_url(title, entries)  (exact → prefix)
    │
    ▼
filter_valid_jobs() + assert_scrape_yielded_jobs() (the 0-result canary)
    │
    ▼
upsert_jobs() - API handles duplicate by URL
    │
    ▼
generate_jobs_markdown() → docs/jobs.md + docs/company.json
    └── committed to repo by CI → available on GitHub Pages
```

## File Responsibilities

| File | Role |
|------|------|
| `config/company.json` | **Single source of truth** for company identity (CIF, brand, URLs) |
| `config/scraper.json` | Source config: careers-site sitemap/listing/jobArchive URLs, CSS selectors, delays, `ownJobUrlPrefix` |
| `scraper/main.py` | Main entry point — full workflow: validate company → scrape → transform → upsert → generate docs |
| `scraper/company.py` | Validates company via ANAF + CUIScan + Peviitor; caches in `tmp/company.json` (7-day TTL) |
| `scraper/anaf.py` | Multi-source company data module — ANAF + CUIScan (company details) + CUIFirma (search) |
| `scraper/api.py` | Peviitor API operations module — query, delete, upsert jobs + company upsert |
| `scraper/validate_jobs.py` | Manual deep validator (content-aware); thin CLI wrapper over `scraper/job_validator.py` |
| `scraper/job_validator.py` | Shared validation primitives: `validate_by_head`, `validate_by_content`, `validate_by_browser`, `DEFAULT_EXPIRED_KEYWORDS` |
| `scraper/self_healing.py` | **Generic** selector cascade — see `ai/AGENTS.md` |
| `scraper/validate.py` | **Generic** pre-publish data validation + the 0-result canary |
| `scraper/markdown_generator.py` | Generates `docs/jobs.md` with company info and all scraped jobs |
| `scraper/parse.py` | Site-specific `parse_listing`, driven by the self-healing cascade |
| `scraper/fetch.py` | HTTP with retry + backoff |
| `scraper/config.py` | Loads `config/company.json` + `config/scraper.json` |

## API Endpoints

- **DemoANAF Company**: `https://demoanaf.ro/api/company/:cui` — company details by CIF
- **DemoANAF Search**: `https://demoanaf.ro/api/search?q=BRAND` — search companies by name/brand
- **CUIScan**: `https://cuiscan.ro/api.php?action=company&cui=CIF` — company details fallback
- **CUIFirma Search**: `https://cuifirma.ro/api/search?q=BRAND` — search fallback
- **Peviitor API**: `https://api.peviitor.ro/v1/` — all job and company operations go through this API
- **Logifuture — listing**: `https://apply.workable.com/logifuture/` — pagina publică de posturi deschise
- **Logifuture — sitemap**: `` — permalink-uri canonice

## Rate Limiting & Politeness

The scraper is intentionally slow to be a good citizen:

| Setting | Value | Where |
|---------|-------|-------|
| Request timeout | 10 s | `config/scraper.json` — `requestTimeoutSec` |
| ANAF fallback | 1 attempt ANAF → CUIScan | `scraper/anaf.py` — no retries, just fallback |
| Concurrency | 1 (sequential) | no concurrent fetches |
| User-Agent | `job_seeker_ro_spider` | identifies the scraper in server logs |
| Page delay | 1 s between requests | `config/scraper.json` — `pageDelaySec` |

Derived scrapers should keep these defaults unless the target site explicitly permits otherwise.

## Standalone Commands

```bash
# Validate job URLs from SOLR by CIF (check active/expired)
python -m scraper.validate_jobs <CIF>

# Validate a single job URL
python -m scraper.validate_jobs --url <url>

# Delete expired jobs from SOLR by CIF
python -m scraper.validate_jobs <CIF> --delete
```

## Testing

This project requires multiple levels of testing:

1. **Unit Tests** — test individual modules (`api.py`, `company.py`, `anaf.py`, ...) in isolation
2. **Integration Tests** — test API interactions (ANAF, Peviitor, SOLR) in `tests/integration/`
3. **E2E Tests** — test the full workflow against the real careers site in `tests/e2e/`
4. **Consistency Tests** — verify repo/doc structure in `tests/consistency/`

Run tests:
```bash
pytest -q
```

## Temporary Files

All temporary/scratch files must be placed in `tmp/` inside the project root
(never outside the project). The `tmp/` directory is in `.gitignore` and will
not be committed.
