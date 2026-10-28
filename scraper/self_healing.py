"""Self-healing extraction primitives.

A single field is extracted through a CASCADE of strategies, tried in order
until one yields a non-empty value:

    1. primary CSS selector          (from config/scraper.json)
    2. one or more fallback CSS selectors
    3. structural anchoring           (itemprop / aria-* / <meta content> / JSON-LD)
    4. regex on the raw HTML          (last-resort safety net)
    (+) optional: Scrapling adaptive relocation  -- see `scrapling_text`

Each strategy runs in its own ``try/except`` -- a raising or empty strategy is
logged and the cascade moves on, so one broken selector never takes the whole
run down. When a fallback rescues a field, that is logged too, so a drifting
site surfaces in the run output immediately.

This module has NO site-specific knowledge -- copy it verbatim into a derived
scraper. ``scraper/parse.py`` is the consumer.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from bs4 import BeautifulSoup, Tag

log = logging.getLogger("scraper.self_healing")

_WS = re.compile(r"\s+")


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return _WS.sub(" ", value).strip()
    return value


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


Strategy = tuple[str, Callable[[], Any]]


@dataclass
class Match:
    value: Any = None
    strategy: str | None = None
    failures: list[str] = field(default_factory=list)


def first_match(label: str, strategies: Sequence[Strategy], *, silent: bool = False) -> Match:
    """Run ``strategies`` in order; return the first non-empty result.

    Args:
        label: human name of the field, for logs.
        strategies: ``(name, callable)`` pairs, tried top to bottom.
        silent: suppress the "all failed" warning (for optional fields).
    """
    failures: list[str] = []

    for name, run in strategies:
        try:
            value = run()
        except Exception as exc:  # noqa: BLE001 - a broken strategy must not be fatal
            failures.append(f"{name}: {exc}")
            continue

        if not _is_empty(value):
            if failures:
                log.info('%s: recovered via "%s" (after %s)', label, name, "; ".join(failures))
            return Match(value=_clean(value), strategy=name, failures=failures)
        failures.append(f"{name}: empty")

    if not silent:
        log.warning("%s: ALL strategies failed -- %s", label, "; ".join(failures) or "no strategies")
    return Match(value=None, strategy=None, failures=failures)


# ---------------------------------------------------------------------------
# Strategy builders
# ---------------------------------------------------------------------------

def as_list(selector_or_list: str | Sequence[str] | None) -> list[str]:
    """Normalise a config value that may be a single selector or a list."""
    if selector_or_list is None:
        return []
    if isinstance(selector_or_list, str):
        return [selector_or_list]
    return [s for s in selector_or_list if s]


def css_text(scope: Tag, selector: str) -> Strategy:
    """Text of the first element matching ``selector`` under ``scope``."""

    def run() -> str | None:
        el = scope.select_one(selector)
        return el.get_text(" ", strip=True) if el else None

    return (f'css("{selector}")', run)


def css_attr(scope: Tag, selector: str, attr: str) -> Strategy:
    """Attribute of the first element matching ``selector`` under ``scope``."""

    def run() -> str | None:
        el = scope.select_one(selector)
        return el.get(attr) if el else None

    return (f'css("{selector}")[{attr}]', run)


def structural_text(scope: Tag, hooks: Sequence[str]) -> Strategy:
    """Try stable structural hooks (itemprop, aria-label, <meta content>)."""

    def run() -> str | None:
        for hook in hooks:
            el = scope.select_one(hook)
            if el is None:
                continue
            text = el.get_text(" ", strip=True) or el.get("content") or el.get("aria-label")
            if text and text.strip():
                return text
        return None

    return (f"structural({'|'.join(hooks)})", run)


def text_from_html(fragment: str | None) -> str | None:
    """Strip tags and collapse whitespace from an HTML fragment."""
    if not fragment:
        return None
    return _clean(BeautifulSoup(str(fragment), "lxml").get_text(" ", strip=True)) or None


def regex_text(html: str, pattern: str | re.Pattern[str], group: int = 1) -> Strategy:
    """Last-resort regex against a raw HTML string; the captured group is de-tagged."""
    rx = re.compile(pattern, re.I | re.S) if isinstance(pattern, str) else pattern

    def run() -> str | None:
        m = rx.search(str(html))
        return text_from_html(m.group(group)) if m else None

    return (f"regex({rx.pattern})", run)


def scrapling_text(html: str, selector: str, *, adaptive: bool = True, auto_save: bool = True) -> Strategy:
    """OPTIONAL adaptive strategy backed by Scrapling.

    Scrapling fingerprints the element the first time it is found (``auto_save``)
    and relocates it by similarity when the selector later drifts
    (``adaptive``). It only helps with *incremental* DOM changes, not a full
    rewrite -- it complements the cascade, it does not replace validation.

    Install with ``pip install "peviitor-scraper-py[adaptive]"`` (or
    ``pip install scrapling``). If Scrapling is not installed this strategy is
    a no-op that returns ``None`` and the cascade simply moves on.
    """

    def run() -> str | None:
        try:
            from scrapling.parser import Adaptor  # type: ignore
        except ImportError:
            log.debug("scrapling not installed -- skipping adaptive strategy for %r", selector)
            return None

        page = Adaptor(body=html, url=None, keep_comments=False, auto_match=auto_save)
        found = page.css(selector, auto_save=auto_save, adaptive=adaptive)
        if not found:
            return None
        first = found[0]
        return getattr(first, "text", None) or first.get_all_text(strip=True)

    return (f'scrapling("{selector}")', run)


# ---------------------------------------------------------------------------
# JSON-LD (schema.org JobPosting)
# ---------------------------------------------------------------------------

def json_ld_job_postings(soup: BeautifulSoup) -> list[dict]:
    """Every schema.org JobPosting embedded in <script type="application/ld+json">.

    Handles a bare object, an array, and an ItemList / @graph wrapper. Malformed
    blocks are skipped, not fatal.
    """
    postings: list[dict] = []

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            continue

        def visit(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    visit(item)
                return
            if not isinstance(node, dict):
                return
            node_type = node.get("@type")
            if node_type == "JobPosting" or (isinstance(node_type, list) and "JobPosting" in node_type):
                postings.append(node)
            for key in ("itemListElement", "@graph"):
                if isinstance(node.get(key), list):
                    visit(node[key])
            if "item" in node:
                visit(node["item"])

        visit(parsed)

    return postings


# ---------------------------------------------------------------------------
# Article-level cascade: how to even find the repeated job blocks
# ---------------------------------------------------------------------------

class _Scope:
    """Mode-agnostic wrapper around one job block."""

    def __init__(self, node: Tag, kind: str) -> None:
        self._node = node
        self.kind = kind

    def text(self, selectors: str | Sequence[str]) -> Match:
        for sel in as_list(selectors):
            try:
                el = self._node.select_one(sel)
            except Exception:  # noqa: BLE001 - invalid selector, try next
                continue
            if el is not None:
                value = _clean(el.get_text(" ", strip=True))
                if value:
                    return Match(value=value, strategy=f'css("{sel}")')
        return Match(value=None, strategy=None)

    def href(self, selectors: str | Sequence[str] | None = None) -> Match:
        """First real (non-fragment, non-``javascript:``) ``href`` in this
        block: from ``selectors`` if given, else the first ``<a href>``
        anywhere in the block. A block usually holds exactly one meaningful
        link (a "view details" / "apply" button, or the title itself
        wrapped in ``<a>``) -- this is a much stronger signal than guessing
        the URL from the title, which breaks the moment the real permalink
        needs an ID segment the title can't reproduce."""
        for sel in as_list(selectors):
            try:
                el = self._node.select_one(sel)
            except Exception:  # noqa: BLE001 - invalid selector, try next
                continue
            if el is not None:
                value = (el.get("href") or "").strip()
                if value and not value.startswith(("#", "javascript:")):
                    return Match(value=value, strategy=f'css("{sel}")[href]')
        for a in self._node.select("a[href]"):
            value = (a.get("href") or "").strip()
            if value and not value.startswith(("#", "javascript:")):
                return Match(value=value, strategy="first-anchor-href")
        return Match(value=None, strategy=None)

    def full_text(self) -> str:
        return _clean(self._node.get_text(" ", strip=True))

    def raw(self) -> str:
        return str(self._node)


@dataclass
class ArticleSet:
    mode: str
    scopes: list[_Scope]
    json_ld: list[dict]


_ARTICLE_RX = re.compile(r"<article\b[^>]*>.*?</article>", re.I | re.S)
_COMMENT_RX = re.compile(r"<!--.*?-->", re.S)


def locate_articles(html: str, article_selectors: str | Sequence[str]) -> ArticleSet:
    """Locate the repeated job blocks on a listing page.

    Returns an ``ArticleSet`` whose ``mode`` is one of:
        ``css:<selector>``  -- matched an article-container selector
        ``jsonld``          -- no article markup, but JobPosting JSON-LD exists
        ``regex:<article>`` -- fell back to slicing <article>...</article>
        ``none``            -- nothing found (the caller's canary should fire)
    """
    soup = BeautifulSoup(html, "lxml")

    for sel in as_list(article_selectors):
        try:
            els = soup.select(sel)
        except Exception:  # noqa: BLE001
            log.warning('article selector "%s" is invalid -- skipping', sel)
            continue
        if els:
            return ArticleSet(mode=f"css:{sel}", scopes=[_Scope(el, "css") for el in els], json_ld=[])

    json_ld = json_ld_job_postings(soup)
    if json_ld:
        return ArticleSet(mode="jsonld", scopes=[], json_ld=json_ld)

    chunks = _ARTICLE_RX.findall(_COMMENT_RX.sub("", html))
    if chunks:
        log.warning(
            "no article selector matched -- falling back to regex <article> slicing (%d blocks)",
            len(chunks),
        )
        scopes = [_Scope(BeautifulSoup(chunk, "lxml"), "regex") for chunk in chunks]
        return ArticleSet(mode="regex:<article>", scopes=scopes, json_ld=[])

    return ArticleSet(mode="none", scopes=[], json_ld=[])
