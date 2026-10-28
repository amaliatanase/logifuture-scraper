import logging

import pytest
from bs4 import BeautifulSoup

from scraper.self_healing import (
    as_list,
    css_text,
    first_match,
    json_ld_job_postings,
    locate_articles,
    regex_text,
    structural_text,
    text_from_html,
)


# --------------------------------------------------------------------------
# first_match — the cascade primitive
# --------------------------------------------------------------------------

class TestFirstMatch:
    def test_primary_wins_and_is_trimmed(self, caplog):
        with caplog.at_level(logging.INFO):
            res = first_match("field", [
                ("primary", lambda: "  hello  "),
                ("fallback", lambda: "world"),
            ])
        assert res.value == "hello"
        assert res.strategy == "primary"
        assert "recovered via" not in caplog.text

    def test_falls_through_when_primary_empty(self, caplog):
        with caplog.at_level(logging.INFO):
            res = first_match("field", [
                ("primary", lambda: ""),
                ("backup", lambda: "recovered"),
            ])
        assert res.value == "recovered"
        assert res.strategy == "backup"
        assert 'recovered via "backup"' in caplog.text

    def test_falls_through_when_primary_raises(self, caplog):
        def boom():
            raise RuntimeError("selector blew up")

        with caplog.at_level(logging.INFO):
            res = first_match("field", [
                ("primary", boom),
                ("backup", lambda: "still fine"),
            ])
        assert res.value == "still fine"
        assert "selector blew up" in caplog.text

    def test_regex_is_the_last_resort(self):
        res = first_match("title", [
            ("css-primary", lambda: None),
            ("css-backup", lambda: ""),
            regex_text("<h3>From Regex</h3>", r"<h3>(.*?)</h3>"),
        ])
        assert res.value == "From Regex"
        assert res.strategy.startswith("regex")

    def test_all_fail_returns_none_and_warns_once(self, caplog):
        def boom():
            raise ValueError("boom")

        with caplog.at_level(logging.WARNING):
            res = first_match("doomed", [("a", lambda: None), ("b", boom)])
        assert res.value is None and res.strategy is None
        assert res.failures == ["a: empty", "b: boom"]
        assert caplog.text.count("ALL strategies failed") == 1

    def test_silent_suppresses_the_all_failed_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            first_match("optional", [("a", lambda: None)], silent=True)
        assert "ALL strategies failed" not in caplog.text


def test_as_list():
    assert as_list("a") == ["a"]
    assert as_list(["a", "b"]) == ["a", "b"]
    assert as_list(["a", "", None, "b"]) == ["a", "b"]
    assert as_list(None) == []


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------

def test_css_and_structural_text():
    soup = BeautifulSoup(
        '<div id="s"><span class="t">CSS Title</span>'
        '<meta itemprop="title" content="Structural Title"></div>',
        "lxml",
    )
    scope = soup.select_one("#s")
    assert css_text(scope, ".t")[1]() == "CSS Title"
    assert structural_text(scope, ["[itemprop='title']"])[1]() == "Structural Title"


# --------------------------------------------------------------------------
# _Scope.href — the URL cascade (real <a href>, not a guessed permalink)
# --------------------------------------------------------------------------

def _scope_for(html: str):
    return locate_articles(f"<div>{html}</div>", "div").scopes[0]


class TestScopeHref:
    def test_finds_the_only_anchor_with_no_selector_given(self):
        scope = _scope_for('<h2>Title</h2><a class="btn" href="/jobs/jr1/title/">View</a>')
        assert scope.href().value == "/jobs/jr1/title/"

    def test_prefers_an_explicit_selector_when_given(self):
        scope = _scope_for(
            '<a class="social" href="https://x.example/">X</a>'
            '<a class="apply" href="/jobs/jr1/title/">Apply</a>'
        )
        assert scope.href(".apply").value == "/jobs/jr1/title/"

    def test_falls_back_to_first_anchor_when_the_selector_misses(self):
        scope = _scope_for('<a href="/jobs/jr1/title/">Apply</a>')
        assert scope.href(".nonexistent").value == "/jobs/jr1/title/"

    def test_ignores_fragment_and_javascript_links(self):
        scope = _scope_for(
            '<a href="#">Save</a><a href="javascript:void(0)">Share</a>'
            '<a href="/jobs/jr1/title/">Apply</a>'
        )
        assert scope.href().value == "/jobs/jr1/title/"

    def test_returns_none_when_the_block_has_no_anchor(self):
        scope = _scope_for("<h2>Title</h2><p>no links here</p>")
        assert scope.href().value is None


def test_text_from_html():
    assert text_from_html("<b>Key</b>  Account   <i>Manager</i>") == "Key Account Manager"
    assert text_from_html("") is None
    assert text_from_html(None) is None


# --------------------------------------------------------------------------
# JSON-LD
# --------------------------------------------------------------------------

def test_json_ld_job_postings_shapes():
    soup = BeautifulSoup("""
      <script type="application/ld+json">{"@type":"JobPosting","title":"Solo"}</script>
      <script type="application/ld+json">[{"@type":"JobPosting","title":"InArray"}]</script>
      <script type="application/ld+json">{"@graph":[{"@type":"Org"},{"@type":"JobPosting","title":"InGraph"}]}</script>
    """, "lxml")
    assert sorted(p["title"] for p in json_ld_job_postings(soup)) == ["InArray", "InGraph", "Solo"]


def test_json_ld_ignores_malformed_blocks():
    soup = BeautifulSoup('<script type="application/ld+json">{ not json </script>', "lxml")
    assert json_ld_job_postings(soup) == []


# --------------------------------------------------------------------------
# locate_articles — article-level cascade
# --------------------------------------------------------------------------

class TestLocateArticles:
    def test_css_primary(self):
        html = '<article class="job-item"><h3>A</h3></article><article class="job-item"><h3>B</h3></article>'
        r = locate_articles(html, ["article.job-item", ".fallback"])
        assert r.mode == "css:article.job-item"
        assert len(r.scopes) == 2
        assert r.scopes[0].text(["h3"]).value == "A"

    def test_css_fallback(self):
        r = locate_articles('<li class="vacancy"><h3>Only fallback</h3></li>', ["article.job-item", "li.vacancy"])
        assert r.mode == "css:li.vacancy"
        assert r.scopes[0].text(["h3"]).value == "Only fallback"

    def test_jsonld_mode(self):
        html = '<script type="application/ld+json">{"@type":"JobPosting","title":"From LD"}</script>'
        r = locate_articles(html, ["article.job-item"])
        assert r.mode == "jsonld"
        assert r.json_ld[0]["title"] == "From LD"

    def test_regex_article_mode(self):
        r = locate_articles('<article data-x="1"><span>Regex Title</span></article>', [".nope"])
        assert r.mode == "regex:<article>"
        assert len(r.scopes) == 1
        assert "Regex Title" in r.scopes[0].full_text()

    def test_none_mode(self):
        r = locate_articles("<div>plain page</div>", [".nope"])
        assert r.mode == "none"
        assert r.scopes == []

    def test_invalid_selector_is_skipped(self, caplog):
        html = '<article class="job-item"><h3>Still works</h3></article>'
        with caplog.at_level(logging.WARNING):
            r = locate_articles(html, ["a[[[bad", "article.job-item"])
        assert r.mode == "css:article.job-item"


# --------------------------------------------------------------------------
# optional Scrapling layer must not break anything when it is absent
# --------------------------------------------------------------------------

def test_scrapling_text_is_a_noop_without_the_package():
    pytest.importorskip  # noqa: B018 - keep the import available
    try:
        import scrapling  # noqa: F401
        pytest.skip("scrapling IS installed — the no-op branch can't be exercised")
    except ImportError:
        from scraper.self_healing import scrapling_text
        name, run = scrapling_text("<h3>x</h3>", "h3")
        assert name.startswith("scrapling(")
        assert run() is None
