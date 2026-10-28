# Tutorial: from `git clone` to your first commit

A full walkthrough of deriving one company's scraper from this template, with
real terminal output at every step and one complete example session. If you
just want the condensed version, see
[README.md → Deriving a company scraper](README.md#deriving-a-company-scraper).

## Prerequisites

- `git`
- **Node.js 18+** (if you'll pick the JavaScript variant) **or Python 3.10+**
  (if you'll pick the Python variant) — you only need the one you pick, not
  both
- [`gh`](https://cli.github.com/) (optional — only needed for the
  create-and-push step at the end)

## Step 1 — clone the template

```bash
git clone https://github.com/{owner}/Brewtality-3-16.git acme-widgets-scraper
cd acme-widgets-scraper
```

```
Cloning into 'acme-widgets-scraper'...
remote: Enumerating objects: 214, done.
remote: Counting objects: 100% (214/214), done.
remote: Compressing objects: 100% (150/150), done.
Receiving objects: 100% (214/214), 180.42 KiB | 3.20 MiB/s, done.
Resolving deltas: 100% (58/58), done.
```

## Step 2 — run the derivation script

```bash
node setup.js       # …or:  python setup.py
```

Below is a **complete example session** — every prompt the script asks, in the
exact order it asks them, answered for a fictional company (the same one used
in the README example: **ACME WIDGETS SRL**). This is real output, captured by
actually running `setup.js`, not a mock-up:

```
Brewtality-3-16 - derive a scraper
=================================

  JavaScript or Python?  (js / py  or  1 / 2): js

  -> JavaScript it is. Now the company details:

  Company legal name (UPPERCASE, e.g. EXAMPLE COMPANY SRL) (required): ACME WIDGETS SRL
  Commercial brand [ACME]: ACME
  CIF / CUI (digits only, no RO prefix) (required): 12345678
  Company website (https://...) (required): https://www.acmewidgets.ro
  Careers / open-positions page URL (required): https://www.acmewidgets.ro/cariere
  Try to auto-detect a CSS selector for job cards by fetching this page now? (y/N):
  Job sitemap URL (Enter if the site has none) (optional, Enter to skip):
  Canonical job-permalink prefix [https://www.acmewidgets.ro/jobs/]:
  HQ city (required): Cluj-Napoca

  CSS selectors - Enter to rely on the generic fallbacks and tune later:

  Primary selector for one job card/row (optional, Enter to skip):
  Primary selector for the job title (optional, Enter to skip):
  Primary selector for the deadline/meta text (optional, Enter to skip):

  GitHub owner / org (required): acme-dev
  GitHub repo name [acme-widgets-nodejs-scraper]:

  Summary
  -------
  language : JavaScript (scraper-js)
  COMPANY_NAME         ACME WIDGETS SRL
  COMPANY_BRAND        ACME
  CIF                  12345678
  WEBSITE_URL          https://www.acmewidgets.ro
  CAREER_URL           https://www.acmewidgets.ro/cariere
  SITEMAP_URL          (blank -> fallbacks)
  JOB_URL_PREFIX       https://www.acmewidgets.ro/jobs/
  DEFAULT_CITY         Cluj-Napoca
  SELECTOR_JOB_ARTICLE (blank -> fallbacks)
  SELECTOR_JOB_TITLE   (blank -> fallbacks)
  SELECTOR_JOB_META    (blank -> fallbacks)
  GITHUB_OWNER         acme-dev
  GITHUB_REPO          acme-widgets-nodejs-scraper

  Apply? This rewrites the repo in place and cannot be undone. (y/N): y

  -> fresh git repo initialised on branch 'main'.

  OK - Scraper generated for ACME WIDGETS SRL in JavaScript.
    package/module name: acme-widgets-scraper
    intended repo:       github.com/acme-dev/acme-widgets-nodejs-scraper

  Ready for the first commit:
    git add -A && git commit -m "Initial scraper for ACME WIDGETS SRL"
    gh repo create acme-dev/acme-widgets-nodejs-scraper --public --source=. --push

  Next: tune the selectors in scraper/config/scraper.json
        and adapt parseListing in scraper/index.js,
        then run the tests (npm install && npm run test:unit).
```

A few notes on the prompts, in case your answers differ from the example:

- **Commercial brand**, **canonical job-permalink prefix** and **GitHub repo
  name** each show a `[default]` — press Enter to accept it. The other
  required fields (legal name, CIF, website, careers URL, HQ city, GitHub
  owner) will re-ask if you leave them blank.
- **Job sitemap URL** and the **three CSS selectors** are genuinely optional —
  leaving them blank just means the scraper starts out relying on the generic
  fallback cascade instead of a tuned primary selector (see
  [README.md → The self-healing cascade](README.md#the-self-healing-cascade)).
  You can fill those in later, once you've inspected the real page.
- **Auto-detect a CSS selector**, right after the careers URL, is also
  optional. Say `y` and the script does a quick, read-only fetch of that page,
  looks for a repeated class name containing a job-ish keyword (`job`,
  `position`, `career`, `vacan…`, …) or, failing that, repeated `<article>`
  tags, and proposes it as the primary job-card selector — you accept or
  reject it right there. Say `N` (or just Enter) and nothing is fetched; the
  later "Primary selector for one job card/row" prompt behaves exactly as
  before.
- Answering anything other than `js`/`py`/`1`/`2` at the first prompt just
  re-asks it; answering anything other than `y`/`yes` at the final confirm
  aborts with `Aborted - nothing changed.` and leaves the clone untouched.
- If your clone is a linked **git worktree** (`.git` is a pointer file, not a
  directory) rather than a plain clone, the script says so up front. It's
  handled automatically — see Step 5, no different behaviour needed from you.

## Step 3 — what just happened

The script rewrote the clone **in place**:

- deleted `scraper-py/` (the variant you didn't pick);
- deleted `setup.js`, `setup.py`, the template's own `README.md` and
  `CLAUDE.md`, and the template's `.git` history — then immediately ran
  `git init` and pointed `HEAD` at `refs/heads/main`, so the folder has its
  own fresh, independent repository from this point on, on branch `main`
  regardless of your global git config (see Step 5);
- moved everything from `scraper-js/` up to the repo root, then removed the
  now-empty `scraper-js/` folder;
- replaced every `{{PLACEHOLDER}}` across the tree with your answers;
- set `"name"` in `package.json` to `acme-widgets-scraper`.

Your working directory now looks like a plain `scraper-js/` project promoted to
the repo root — `scraper/`, `tests/`, `ai/`, `docs/`, `package.json`, its own
`.github/workflows/`, and so on. Full detail on what's generic vs.
company-specific: [README.md → This is a template](README.md#this-is-a-template--fill-in-the-placeholders).

## Step 4 — run the tests

```bash
npm install && npm run test:unit
```

The unit tests use their own generic fixtures, so they pass immediately —
before you've touched a single selector:

```
  index.js Component Tests
    slugify
      √ strips Romanian diacritics and lowercases
      √ collapses separators and trims dashes
    parseDeadline
      √ converts a DD.MM.YYYY deadline to an end-of-day ISO string
      √ returns undefined when no date is present
    parseListing
      √ extracts one item per article with a decoded, trimmed title
      √ carries the deadline when present, undefined otherwise
      √ returns an empty array when the selector matches nothing
      self-healing when the primary markup breaks
        √ recovers via a fallback article selector when the class is renamed
        √ recovers the title via a fallback heading selector when .job__title is gone
        √ falls back to JSON-LD JobPosting when there is no article markup at all
        √ falls back to regex <article> slicing when the container selectors all miss
        √ returns [] and does not throw when the page is unrecognisable (canary feeds off this)
  ...

Test Suites: 8 passed, 8 total
Tests:       151 passed, 151 total
Snapshots:   0 total
Time:        ~3 s
```

(Python: `pip install -e ".[dev]" && pytest -q`.) Exact test counts and timing
will vary slightly across versions of this template — the point is that
everything is green with zero company-specific setup.

The **integration**, **e2e** and **consistency** suites self-skip for now —
they need the real website, ANAF and the peViitor API to be reachable, and a
real `GITHUB_REPOSITORY`/`GITHUB_TOKEN` for consistency. They start doing real
work once you point the placeholders at a real company (which you already did
in Step 2) and the site/API are reachable from wherever you run them.

## Step 5 — your first commit

The derivation script already ran `git init` for you (that's the
`-> fresh git repo initialised on branch 'main'.` line in Step 2) and forced
the branch name to `main` — no need to run `git init` yourself, and no
`master`-vs-`main` guessing based on your local git config. Just:

```bash
git add -A
git commit -m "Initial scraper for ACME WIDGETS SRL"
```

```
$ git add -A
$ git commit -m "Initial scraper for ACME WIDGETS SRL"
[main (root-commit) 4acdc48] Initial scraper for ACME WIDGETS SRL
 66 files changed, 14618 insertions(+)
 create mode 100644 .github/workflows/job-seeker-ro-spider.yml
 create mode 100644 ai/AGENTS.md
 create mode 100644 package.json
 create mode 100644 scraper/index.js
 create mode 100644 tests/unit/index.test.js
 ...
```

(File/line counts will vary slightly across versions of this template; the
branch is always `main`, regardless of your local git version or config — see
[ai/BRANCH.md](scraper-js/ai/BRANCH.md) / the Python variant's copy.)

## Step 6 — optional: create the GitHub repo and push

```bash
gh repo create acme-dev/acme-widgets-nodejs-scraper --public --source=. --push
```

Set the repo's topics right after — the convention is exactly 2 topics,
`job-seeker-ro-spider` and `peviitor-ro` (see
[`ai/TOPICS.md`](ai/TOPICS.md) once the derivation is done, or
[`scraper-js/ai/TOPICS.md`](scraper-js/ai/TOPICS.md) in this template repo):

```bash
gh repo edit acme-dev/acme-widgets-nodejs-scraper \
  --add-topic job-seeker-ro-spider --add-topic peviitor-ro
```

## Next steps

- Tune the selectors in `scraper/config/scraper.json` and adapt
  `parseListing` in `scraper/index.js` (or `parse_listing` in `scraper/parse.py`)
  to the real site's markup.
- If you're driving this with Claude Code or another AI agent, **[ai/PROMPTS.md](ai/PROMPTS.md)**
  has ready-to-use prompts for each of these stages — checking a target
  company before you start, deriving, creating the repo and pushing,
  diagnosing a red CI run, and verifying the self-healing fallbacks actually
  work.
- For how the self-healing cascade and the canary work in detail:
  [`scraper-js/ai/AGENTS.md`](scraper-js/ai/AGENTS.md) ·
  [`scraper-py/ai/SELF-HEALING.md`](scraper-py/ai/SELF-HEALING.md).
