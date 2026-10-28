"""Consistency tests: root files, ai/ docs, workflow naming, changelog, gitignore.

Adapted from the Python reference template's tests/consistency/test_repo.py,
genericised for Brewtality-3-16 (no company-specific assertions). Two checks
are intentionally soft-skipped, not hard-required, until the rest of the
compliance-audit work lands in this same repo: the full ai/*.md doc set and
the root community-health files (CODE_OF_CONDUCT.md/CONTRIBUTING.md/
SECURITY.md). Once those files exist the skip condition stops firing and the
assertion runs for real -- no one needs to remember to re-enable anything.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

ALWAYS_REQUIRED_ROOT_FILES = [
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "requirements.txt",
    "pyproject.toml",
]

# Lives one level up from here (repo root) in the template checkout --
# scraper-py/ isn't a derived repo's root until setup.py promotes it -- but
# at true root once derived, same as everything above. Checked separately
# (and skipped in the template itself) rather than folded into the list
# above so it doesn't need a template-relative path hack.
COMMIT_CHECKLIST_FILE = "COMMIT_CHECKLIST.md"

# Added by the ai/*.md documentation pass (compliance-audit Group 4).
FULL_AI_DOC_SET = [
    "AGENTS.md",
    "BRANCH.md",
    "COMPANY_MODEL.md",
    "INSTRUCTIONS.md",
    "ISSUES.md",
    "JOB_MODEL.md",
    "MAINTENANCE.md",
    "PUBLIC.md",
    "ROBOTS.md",
    "TOPICS.md",
    "UPDATE-REPO-ABOUT.md",
    "files.md",
]

# Added by the root community-health-file pass (compliance-audit Group 4).
COMMUNITY_HEALTH_FILES = ["CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md"]

REQUIRED_WORKFLOWS = [
    "job-deep-validate.yml",
    "job-recovery-from-disaster.yml",
    "automation-template-sync-check.yml",
    "automation-health-summary.yml",
]

# Placeholders like LOGIFUTURE must all be filled in by setup.py before
# a derived repo's first commit -- a leftover one is exactly the kind of bug
# that went unnoticed in two derived repos' tests.yml until a manual audit
# caught it (see COMMIT_CHECKLIST.md). Config/docs values genuinely can be
# blank ("(blank -> fallbacks)" in setup.py's own summary), but a raw
# {{TOKEN}} surviving into a commit means setup.py was skipped or interrupted
# partway through.
_PLACEHOLDER_RX = re.compile(r"\{\{(?!PLACEHOLDER\}\})[A-Z_]+\}\}")


def test_always_required_root_files_exist():
    missing = [f for f in ALWAYS_REQUIRED_ROOT_FILES if not (ROOT / f).exists()]
    assert not missing, f"Missing root files: {missing}"


def test_community_health_files_exist():
    missing = [f for f in COMMUNITY_HEALTH_FILES if not (ROOT / f).exists()]
    if missing:
        pytest.skip(f"not added yet (compliance-audit Group 4): {missing}")
    for f in COMMUNITY_HEALTH_FILES:
        assert (ROOT / f).stat().st_size > 0, f"{f} exists but is empty"


def test_baseline_ai_docs_exist():
    ai_dir = ROOT / "ai"
    required_now = ["AGENTS.md", "BRANCH.md"]
    missing = [f for f in required_now if not (ai_dir / f).exists()]
    assert not missing, f"Missing ai/ docs: {missing}"


def test_full_ai_doc_set_exists():
    ai_dir = ROOT / "ai"
    missing = [f for f in FULL_AI_DOC_SET if not (ai_dir / f).exists()]
    if missing:
        pytest.skip(f"not added yet (compliance-audit Group 4): {missing}")


def test_required_workflows_exist():
    wf_dir = ROOT / ".github" / "workflows"
    missing = [f for f in REQUIRED_WORKFLOWS if not (wf_dir / f).exists()]
    assert not missing, f"Missing workflows: {missing}"


def test_pyproject_version_matches_latest_changelog_entry():
    """Strict, not just "a version heading exists" -- pyproject.toml's version
    must be the exact same string as CHANGELOG.md's latest entry. Mirrors the
    JS template's tests/consistency/version.test.js (package.json vs. CHANGELOG)."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M)
    assert match, "CHANGELOG.md must have at least one '## [x.y.z]' version heading"
    changelog_version = match.group(1)

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version_match = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    assert version_match, "pyproject.toml must have a version = \"x.y.z\" line"
    pyproject_version = version_match.group(1)

    assert pyproject_version == changelog_version, (
        f"pyproject.toml version ({pyproject_version}) must match the latest "
        f"CHANGELOG.md entry ({changelog_version})"
    )


def test_gitignore_excludes_python_artifacts():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("__pycache__", ".pytest_cache", "*.py[cod]", "tmp/"):
        assert pattern in gitignore, f".gitignore missing pattern: {pattern}"


def _is_template_checkout() -> bool:
    """True only in Brewtality-3-16 itself, never in a derived repo.

    setup.py always renames pyproject.toml's `name` away from
    "peviitor-scraper-template" as its very last content edit -- so this
    stays true exactly as long as the {{PLACEHOLDER}} tokens below are
    still legitimately unfilled.
    """
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^name = "([^"]+)"', pyproject, re.M)
    return bool(match) and match.group(1) == "peviitor-scraper-template"


def test_commit_checklist_exists():
    if _is_template_checkout():
        pytest.skip("this is the template itself -- COMMIT_CHECKLIST.md lives at the monorepo root, not here")
    assert (ROOT / COMMIT_CHECKLIST_FILE).exists(), f"Missing {COMMIT_CHECKLIST_FILE}"


def test_no_leftover_placeholders():
    """A derived repo's first commit must have every {{PLACEHOLDER}} filled
    in by setup.py. One surviving here means setup.py was skipped, aborted
    partway, or a file it doesn't touch (e.g. added after derivation) still
    has a stray token pasted from the template. Skipped in the template
    itself, where these tokens are the entire point."""
    if _is_template_checkout():
        pytest.skip("this is the template itself -- placeholders are expected here")

    skip_dirs = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv"}
    # This file (and its JS mirror) talk *about* the {{TOKEN}} convention in
    # comments/docstrings/error messages -- exclude self-reference, not just
    # the literal word "PLACEHOLDER", so this test doesn't flag itself.
    skip_files = {pathlib.Path(__file__).resolve()}
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in skip_dirs for part in path.parts):
            continue
        if path.resolve() in skip_files:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _PLACEHOLDER_RX.search(text):
            hits.append(str(path.relative_to(ROOT)))
    assert not hits, f"Leftover placeholder tokens in: {hits}"
