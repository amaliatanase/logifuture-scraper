# Self-healing selector cascade

`scraper/self_healing.py` + `scraper/validate.py` are **generic** (no site
knowledge) — copy them verbatim into a derived scraper. Only
`config/scraper.json` and `scraper/parse.py` are site-specific.

## How a field is extracted

Every field on the listing page goes through a cascade, tried top to bottom
until one strategy returns a non-empty value. Each step is wrapped in its own
`try/except` — a raising or empty strategy is **logged**
(`scraper.self_healing: <field>: …`) and the cascade continues, so one broken
selector never fails the run, and a fallback that rescues a field is printed
immediately (not discovered two weeks later).

| Level | Strategy | Builder | Where it's configured |
|---|---|---|---|
| 1 | Primary CSS selector | `css_text` | first entry of `selectors.*` in `config/scraper.json` |
| 2 | Fallback CSS selectors | `css_text` | remaining entries of that array |
| 3 | Structural anchoring | `structural_text`, `json_ld_job_postings` | `[itemprop]`, `[aria-label]`, `<meta content>`, **JSON-LD `JobPosting`** |
| 4 | Regex on raw HTML | `regex_text` | `<hN>` / `<a>` capture, de-tagged — last resort |
| 5 *(optional)* | **Scrapling** adaptive relocation | `scrapling_text` | `adaptive=True, auto_save=True` — no-op if `scrapling` isn't installed |

The **article-level** cascade (finding the repeated job blocks at all) works the
same way — `locate_articles()` returns a `mode`:

```
css:<selector>  →  jsonld  →  regex:<article>  →  none  (canary fires)
```

## Scrapling — the optional level 5

[Scrapling](https://github.com/D4Vinci/Scrapling) fingerprints an element the
first time it is located (`auto_save=True`) and, when the selector later drifts,
relocates it by structural/text similarity (`adaptive=True`). It only helps with
**incremental** DOM changes, not a full rewrite — it complements the cascade and
validation, it does not replace them.

```python
from scraper.self_healing import first_match, css_text, scrapling_text, regex_text

first_match("job title", [
    css_text(scope, ".header-job h3"),                 # 1 primary
    css_text(scope, "h1, h2, h3, h4"),                 # 2 fallback
    scrapling_text(scope.raw(), ".header-job h3"),     # 5 adaptive (optional)
    regex_text(scope.raw(), r"<h[1-4][^>]*>(.*?)</h[1-4]>"),  # 4 last resort
])
```

Install: `pip install -e ".[adaptive]"` (or `pip install scrapling`). Without it,
`scrapling_text` logs a debug line and returns `None`; the cascade moves on.

Scrapling saves its fingerprints to a file (`.scrapling` by default) — commit it
so the fingerprints survive between CI runs, or accept a cold start each run.

## JS ↔ Python parity

The JS half (`../scraper-js/`) implements the **same cascade** in
`scraper/self-healing.js` — Cheerio has no Scrapling equivalent, so JS does
levels 1–4 by hand. The two are deliberately kept in step:

| Concept | JS (`self-healing.js`) | Python (`self_healing.py`) |
|---|---|---|
| cascade primitive | `firstMatch(label, strategies)` | `first_match(label, strategies)` |
| article locator | `locateArticles(html, selectors)` | `locate_articles(html, selectors)` |
| JSON-LD | `jsonLdJobPostings($)` | `json_ld_job_postings(soup)` |
| builders | `cssText`, `structuralText`, `regexText` | `css_text`, `structural_text`, `regex_text` |
| adaptive | — (n/a) | `scrapling_text` |
| validation | `validate.js` | `validate.py` |
| canary | `assertScrapeYieldedJobs` | `assert_scrape_yielded_jobs` |

## Adding a field to a derived scraper

1. Add its selector list to `selectors` in `config/scraper.json` (primary + 1–2 fallbacks).
2. In `parse_listing`, extract it with `first_match("<field>", [ …strategies ])`
   or `scope.text(selectors)` for the plain CSS cascade.
3. Compose strategies from `css_text`, `structural_text`, `regex_text`,
   `json_ld_job_postings`, and optionally `scrapling_text`.
4. Add a test per level in `tests/test_self_healing.py` / `tests/test_parse.py`
   (primary works → fallback works → regex works → all-fail logs).

## URL extraction (`Scope.href`) and live validation

`parse_listing` also extracts each job's real URL via `Scope.href(selectors)`:
an explicit selector's `href` if given, else the first real (non-`#`,
non-`javascript:`) `<a href>` anywhere in the block. This is deliberately a
**scraped fact, not a guess** — `main.py::scrape_careers()` only falls back to
a sitemap match, then to `f"{archive}{slugify(title)}/"`, when the block had
no anchor at all. A slug guessed from the title can never reproduce a
permalink that embeds an ID (`/jobs/jr133930/software-architect/`), which is
exactly what silently sent 404ing URLs to peviitor before this field existed.

As a second, independent safety net, `main.py::run()` GET-checks every job
URL via `job_validator.validate_by_content()` right before upload
(`_drop_dead_urls`) and drops whatever doesn't resolve — `validate_job` only
checks URL *shape* (a syntactically valid http(s) string), it was never able
to catch a 404. `validate_by_content`, not `validate_by_head`: at least one
real careers site (Workday-based) answers *every* HEAD request with a generic
404 regardless of whether the resource exists — HEAD-only would have dropped
every real job.

## Validation & canary (`scraper/validate.py`)

- `validate_job(job)` → `(is_valid, errors)`: URL must be a real http(s) URL,
  title non-empty / no HTML / ≤ 200 chars, `location` a list of non-empty
  strings, `salary` a string with no negative amount.
- `filter_valid_jobs(jobs)` drops the failures (logged individually) before the job model.
- `assert_scrape_yielded_jobs(jobs)` raises `CanaryError` **before any write**
  when the scrape produced nothing (or nothing survived validation).
