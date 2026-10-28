"""Consistency tests for CODE_OF_CONDUCT.md.

Genericised from the Python reference template's version (drops the
"Asociația Oportunități și Cariere"-specific values/contact assertions --
those are meaningful only for a derived, community-run repo, not this
template). Asserts the document stays a full Contributor Covenant 2.0
(matching the version already shipped in scraper-js's own CODE_OF_CONDUCT.md).

Soft-skips until CODE_OF_CONDUCT.md is added (compliance-audit Group 4);
once it exists, every assertion below runs for real.
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CODE_OF_CONDUCT_PATH = ROOT / "CODE_OF_CONDUCT.md"

REQUIRED_SECTIONS = [
    "## Our Pledge",
    "## Our Standards",
    "## Enforcement Responsibilities",
    "## Scope",
    "## Enforcement",
    "## Attribution",
]


def _code_of_conduct() -> str:
    if not CODE_OF_CONDUCT_PATH.exists():
        pytest.skip("CODE_OF_CONDUCT.md not added yet (compliance-audit Group 4)")
    return CODE_OF_CONDUCT_PATH.read_text(encoding="utf-8")


def test_code_of_conduct_required_sections():
    coc = _code_of_conduct()
    missing = [s for s in REQUIRED_SECTIONS if s not in coc]
    assert not missing, f"CODE_OF_CONDUCT.md missing required sections: {missing}"


def test_code_of_conduct_attribution():
    coc = _code_of_conduct()
    assert "Contributor Covenant" in coc, "CODE_OF_CONDUCT.md must credit the Contributor Covenant"
    assert "2.0" in coc, "CODE_OF_CONDUCT.md must state the adapted version"
