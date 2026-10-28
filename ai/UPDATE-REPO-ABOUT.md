# Update Repo About

`gh repo create` does NOT set any of this. Skipping it is not cosmetic --
the consistency tests hit the GitHub API in CI and FAIL on the very first
push if these are missing (test_topics.py, test_repo.py "GitHub Pages URL
set in About").

## Description
Scraper automat pentru locurile de muncă LOGIFUTURE (CIF: 49014718) — extrage de pe https://apply.workable.com/logifuture/, validează via ANAF și publică pe peviitor.ro

## Topics (exactly 2, per TOPICS.md)
- job-seeker-ro-spider
- peviitor-ro

## Homepage (About > Website) + GitHub Pages
Required by `tests/consistency/test_repo.py` ("must have GitHub Pages URL
set in About"). Set the homepage AND actually enable Pages -- setting only
the homepage field leaves the URL 404ing:
```
gh repo edit <owner>/<repo> --add-topic job-seeker-ro-spider --add-topic peviitor-ro \
  --homepage "https://<owner-lowercase>.github.io/<repo>/" \
  --description "Scraper pentru LOGIFUTURE - peViitor.ro"
gh api -X POST repos/<owner>/<repo>/pages -f build_type=legacy -f "source[branch]=main" -f "source[path]=/docs"
```

## Workflow file
`.github/workflows/scrape.yml`
