# Contributing

Thank you for your interest in contributing!

## Development Setup

```bash
pip install -e ".[dev]"
pytest -q
```

## Reporting Issues

Open a [GitHub Issue](https://github.com/amaliatanase/logifuture-scraper/issues) with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior

## Job Sources

A derived scraper extracts jobs from the company's own careers listing
(`https://apply.workable.com/logifuture/`) and its job sitemap (``).

If the careers page changes its DOM structure, update the **selector cascades**
in `config/scraper.json` (primary + fallbacks) — the self-healing cascade in
`scraper/self_healing.py` and the tests in `tests/` mean one broken selector
should not fail a run. Add a test per new fallback level.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
