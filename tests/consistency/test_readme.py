"""Consistency tests for the root README.md.

Adapted from the Python reference template's tests/consistency/test_readme.py
-- genericised (no company-specific board/URL/name assertions, since this
file is the template itself, not a derived company repo).
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
README_PATH = ROOT / "README.md"

REQUIRED_SECTIONS = ["## Quick start", "## Layout", "## License"]


def _readme() -> str:
    return README_PATH.read_text(encoding="utf-8")


def test_readme_has_required_sections():
    readme = _readme()
    missing = [s for s in REQUIRED_SECTIONS if s not in readme]
    assert not missing, f"README.md missing required sections: {missing}"


def test_readme_mentions_peviitor():
    assert "peviitor" in _readme().lower()


def test_readme_license_section_mentions_mit():
    readme = _readme()
    start = readme.index("## License")
    license_section = readme[start:]
    assert "MIT" in license_section
