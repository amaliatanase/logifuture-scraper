"""Consistency tests for .github/workflows/ naming, and cross-checking that
docs/index.html never links to a workflow file that doesn't actually exist.

Mirrors the JS template's tests/consistency/workflow-naming.test.js, plus one
check the JS version doesn't have: the actual bug that motivated writing this
in the first place (docs/index.html referencing job-seeker-ro-spider.yml /
automation-testing.yml -- workflow names from the JS template -- when this
repo's real files are scrape.yml / tests.yml) would have been caught
immediately by a naming-convention test that cross-references real files.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
INDEX_HTML = ROOT / "docs" / "index.html"

_WORKFLOW_LINK_RX = re.compile(r"actions/workflows/([a-zA-Z0-9_.-]+\.yml)")


def _workflow_files() -> list[str]:
    return sorted(f.name for f in WORKFLOWS_DIR.glob("*.yml"))


def test_workflow_files_follow_naming_convention():
    files = _workflow_files()
    assert files, "no workflow files found"
    for f in files:
        assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*\.yml$", f), \
            f"{f} should be lowercase, hyphen-separated, and end in .yml"


def test_no_generic_test_yml():
    assert "test.yml" not in _workflow_files(), \
        "workflow files should be named for what they do, not a generic 'test.yml'"


def test_docs_index_html_never_links_a_nonexistent_workflow():
    if not INDEX_HTML.exists():
        import pytest
        pytest.skip("docs/index.html not present")

    html = INDEX_HTML.read_text(encoding="utf-8")
    referenced = set(_WORKFLOW_LINK_RX.findall(html))
    existing = set(_workflow_files())

    missing = referenced - existing
    assert not missing, (
        f"docs/index.html links to workflow(s) that don't exist in "
        f".github/workflows/: {sorted(missing)} (actual files: {sorted(existing)})"
    )
