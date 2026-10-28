# PUBLIC.md — Repository Must Be PUBLIC

All scrapers derived from this Brewtality-3-16 template **MUST** be **PUBLIC** repositories.

## Why?

- Peviitor is an open-source platform
- Job data should be accessible to everyone
- GitHub Pages requires public repos
- Transparency builds trust

## Enforcement

A CI test (`tests/consistency/`) should verify this repository is public using
the GitHub API. If the repo is private, the test fails.

## How to check

```bash
gh repo view $OWNER/$REPO --json visibility
```
