# scraper-py — Python scraper template

The Python half of the [Brewtality-3-16](../README.md) self-healing job-scraper
template for [peviitor.ro](https://peviitor.ro) ([`scraper-js/`](../scraper-js/)
is the Node.js half). `requests` + BeautifulSoup, pytest, plus an **optional**
adaptive layer via [Scrapling](https://github.com/D4Vinci/Scrapling).

> **This is a template.** `config/*.json` ships `{{PLACEHOLDER}}` values — see
> the [repo-root README](../README.md) for the placeholder list. Copy this
> folder into a new repo and fill them in.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate     # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest                                            # run the suite
python -m scraper.main --dry-run                  # run the pipeline without writing
```

Optional adaptive selectors:

```bash
pip install -e ".[adaptive]"    # pulls in scrapling
```

## Layout

| Path | Role |
|---|---|
| `config/company.json` | company identity — single source of truth |
| `config/scraper.json` | sources, **selector cascades**, retry policy, delays |
| `scraper/self_healing.py` | **generic** cascade: `first_match`, `locate_articles`, `json_ld_job_postings`, `scrapling_text` |
| `scraper/validate.py` | **generic** data validation + `assert_scrape_yielded_jobs` (canary) |
| `scraper/fetch.py` | `requests` + retry / full-jitter backoff |
| `scraper/parse.py` | site-specific: `parse_listing` on the cascade |
| `scraper/api.py` | peviitor API client |
| `scraper/main.py` | orchestration: scrape → validate → canary → upsert → diff |
| `ai/AGENTS.md` | rules + how the cascade works |
| `ai/SELF-HEALING.md` | the cascade in depth, JS↔Python parity, Scrapling notes |

## The cascade in one paragraph

Every field is extracted by trying strategies top to bottom until one returns a
non-empty value: **primary CSS → fallback CSS → structural (itemprop / aria /
JSON-LD) → regex → (optional) Scrapling adaptive relocation**. Each step has its
own `try/except`; a failed or rescued step is logged immediately. If a whole
run scrapes nothing, the **canary** raises before any file or API write. Full
detail in [`ai/SELF-HEALING.md`](ai/SELF-HEALING.md).

## JavaScript-rendered career sites (Playwright)

If the job list is built client-side, `requests` only sees an empty shell. Set
`rendering` in `config/scraper.json`:

```json
"rendering": {"mode": "browser", "waitSelector": ".job-card", "timeoutMs": 30000}
```

`static` (default) never launches a browser; `browser` always renders;
`auto` renders only when the static HTML parses to zero jobs. The scrape
workflow installs Chromium only when the mode is not `static`. Locally:
`python -m playwright install chromium`. Code: `scraper/browser.py`; tests:
`tests/test_browser.py` (fake Playwright, plus one `@pytest.mark.browser` test
against real Chromium, skipped if absent: `pytest -m browser`).

## License

MIT.
