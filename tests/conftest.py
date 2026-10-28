from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent / "fixtures"

# A generic example selector cascade. The template's config/scraper.json ships
# {{PLACEHOLDER}} selectors, so tests pass their own explicitly.
EXAMPLE_SELECTORS = {
    "jobArticle": [".job", "[class*='job']", ".vacancy, .position, .listing-item"],
    "jobTitle": [".job__title", "h1, h2, h3, h4", "[itemprop='title'], [aria-label]", "a"],
    "jobMeta": [".job__meta", "p, .meta, [class*='deadline']"],
}


@pytest.fixture
def selectors():
    return EXAMPLE_SELECTORS


@pytest.fixture
def fixture_html():
    """Return the text of a fixture file under tests/fixtures/."""
    def _load(name: str) -> str:
        return (_FIXTURES / name).read_text(encoding="utf-8")
    return _load
