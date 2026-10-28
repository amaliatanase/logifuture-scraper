# Robots.txt & scraping policy

Fill this in per derived company. Check `https://logifuture.com/robots.txt` before the
first run and confirm the careers listing + sitemap are not disallowed for a
general `User-agent: *`.

## What this scraper reads

| Path | Role |
|---|---|
| `https://apply.workable.com/logifuture/` | Public list of open positions (server-rendered HTML) |
| `` | Job sitemap — canonical `https://logifuture.com/jobs/<slug>/` permalinks |
| `https://logifuture.com/jobs/<slug>/` | Individual job pages (only referenced, not fully crawled) |

## Politeness (defaults — keep unless the site explicitly permits more)

| Measure | Value | Where |
|---|---|---|
| Requests | sequential, one at a time | `scraper/main.py` (no concurrent fetches) |
| Delay between pages | `pageDelaySec` (1.0 s) | `config/scraper.json` |
| Timeout | `requestTimeoutSec` (10 s) | `config/scraper.json` |
| User-Agent | `job_seeker_ro_spider` | identifies the scraper in server logs |
| Retries | exponential backoff, capped | `scraper/fetch.py` |

No assets downloaded, no JS rendered by default (see `scraper/job_validator.py`'s
optional Playwright-backed browser mode for the one exception), no links
followed outside the job-URL prefix. Never bypass a login or authentication wall.
