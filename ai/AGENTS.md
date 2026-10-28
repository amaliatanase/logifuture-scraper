# AGENTS.md — rules for AI agents

## Project
`peviitor-scraper-py` — self-healing job scraper skeleton for peviitor.ro
(Python, `requests` + BeautifulSoup, pytest). The Python counterpart of the
Brewtality-3-16 template (`scraper-js/`).

## Layout & what is generic vs. site-specific

| Generic — copy verbatim into a derived scraper | Site-specific — edit per company |
|---|---|
| `scraper/self_healing.py` | `config/company.json` |
| `scraper/validate.py` | `config/scraper.json` |
| `scraper/fetch.py` | `scraper/parse.py` |
| `scraper/api.py` | (the source URLs in `main.py`) |
| `scraper/anaf.py` (ANAF/CUIScan/CUIFirma lookup) | |
| `scraper/company.py` (ANAF validation + 7-day cache) | |
| `scraper/job_validator.py` (HEAD/content/browser URL checks) | |
| `scraper/validate_jobs.py` (manual deep-validation CLI) | |
| `scraper/markdown_generator.py` (renders `docs/jobs.md`) | |

Never hardcode company identity in source — it lives in `config/company.json`
and is read through `scraper/config.py`.

## Self-healing cascade

Every listing field is extracted by a top-to-bottom cascade of strategies, one
`try/except` each, logged on failure/rescue:

**primary CSS → fallback CSS → structural (itemprop / aria / JSON-LD) → regex → (optional) Scrapling**

Full detail, JS↔Python parity table, and Scrapling notes: **[SELF-HEALING.md](SELF-HEALING.md)**.

## Rules

1. **Tests before commit.** `pytest` must be green. Add a test per new cascade level.
2. **Canary.** `assert_scrape_yielded_jobs` runs before any write. Do not weaken it.
3. **Validation.** New scraped fields go through `validate_job`; extend its rules, don't bypass.
4. **Retry.** All outbound HTTP goes through `scraper/fetch.py` (retry + backoff). Don't call `requests` directly from `parse.py` / `api.py`.
   **Deliberate exception:** `anaf.py`, `company.py`, and `job_validator.py` call
   `requests` directly, bypassing `fetch.py`. This is intentional, not an
   oversight — it mirrors the JS template's `anaf.js` (which documents itself as
   "1 try demoanaf.ro → 1 try cuiscan.ro → cached data. No retries."): ANAF/
   CUIScan/CUIFirma get exactly one attempt per source before the cascade falls
   through to the next one, and retrying each source with `fetch.py`'s backoff
   would multiply that latency for no benefit. Don't "fix" this by routing them
   through `fetch.py` without re-checking that design intent first.
5. **Temp files** in `tmp/` only (gitignored).
6. **Never commit credentials** (`.env.local`, API keys).
7. **Scrapling is optional** — code must run and tests must pass without it installed.

## Commands

```bash
pip install -e ".[dev]"
pytest
pytest tests/test_self_healing.py -q      # just the cascade
python -m scraper.main --dry-run          # full pipeline, no writes
```
