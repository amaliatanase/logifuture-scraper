"""Parse the company's careers listing into job dicts.

The only site-specific module. Every field goes through the self-healing
cascade in ``scraper.self_healing`` driven by ``config/scraper.json``
(``{{PLACEHOLDER}}`` selectors in the template — tests pass their own).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone

from .config import scraper
from .self_healing import (
    first_match,
    locate_articles,
    regex_text,
    scrapling_text,
    text_from_html,
)

log = logging.getLogger("scraper.parse")

_SEL = scraper["selectors"]

# Romanian ș/ț have no NFD decomposition, so map them explicitly.
_DIACRITICS = str.maketrans({"ă": "a", "â": "a", "î": "i", "ș": "s", "ş": "s", "ț": "t", "ţ": "t"})
_NONWORD = re.compile(r"[^a-z0-9]+")
_HN_RX = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>", re.I | re.S)
_A_RX = re.compile(r"<a\b[^>]*>(.*?)</a>", re.I | re.S)
_DMY_RX = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
_ISO_RX = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ][\d:.]+Z?)?")
_RO_COUNTRY_RX = re.compile(r"^(ro|romania|rom[aâ]nia)$", re.IGNORECASE)


def slugify(text: str) -> str:
    lowered = str(text).lower().translate(_DIACRITICS)
    stripped = "".join(c for c in unicodedata.normalize("NFD", lowered) if unicodedata.category(c) != "Mn")
    return _NONWORD.sub("-", stripped).strip("-")


# Light location hint from the title; the final job model still gets its
# location re-validated against ROMANIAN_CITIES before upload. Mirrors
# scraper-js's RO_CITY_HINTS / locationFromTitle exactly.
RO_CITY_HINTS = [
    "Iași", "Iasi", "București", "Bucuresti", "Cluj", "Timișoara", "Timisoara",
    "Ploiești", "Ploiesti", "Constanța", "Constanta", "Brașov", "Brasov",
    "Craiova", "Sibiu", "Oradea", "Bacău", "Bacau", "Galați", "Galati",
    "Dâmbovița", "Dambovita",
]


def location_from_title(title: str, default_location: list[str]) -> list[str]:
    """Cheap location hint scraped straight from the job title; the caller
    still runs the result through ``validate_ro_locations`` before upload."""
    for city in RO_CITY_HINTS:
        if re.search(rf"\b{re.escape(city)}\b", title, re.IGNORECASE):
            return [city]
    return default_location


# Full Romanian-city allowlist used to sanity-check any job location before
# it reaches SOLR -- whether it came from location_from_title, raw scraped
# markup, or ANOFM. Anything not on this list (and not a bare "românia"/
# "romania") silently degrades to the generic ["România"] fallback instead of
# uploading noise (a "Remote" tag, a street address, a typo). Kept identical
# to scraper-js's romanianCities -- this is the JS/Python parity fix.
ROMANIAN_CITIES = [
    'Bucharest', 'București', 'Bucuresti', 'Cluj-Napoca', 'Cluj Napoca',
    'Timișoara', 'Timisoara', 'Iași', 'Iasi', 'Brașov', 'Brasov',
    'Constanța', 'Constanta', 'Craiova', 'Bacău', 'Sibiu',
    'Târgu Mureș', 'Targu Mures', 'Oradea', 'Baia Mare', 'Satu Mare',
    'Ploiești', 'Ploiesti', 'Pitești', 'Pitesti', 'Arad', 'Galați', 'Galati',
    'Brăila', 'Braila', 'Drobeta-Turnu Severin', 'Râmnicu Vâlcea', 'Ramnicu Valcea',
    'Buzău', 'Buzau', 'Botoșani', 'Botosani', 'Zalău', 'Zalau', 'Hunedoara', 'Deva',
    'Suceava', 'Bistrița', 'Bistrita', 'Tulcea', 'Călărași', 'Calarasi',
    'Giurgiu', 'Alba Iulia', 'Slatina', 'Piatra Neamț', 'Piatra Neamt', 'Roman',
    'Dumbrăvița', 'Dumbravita', 'Voluntari', 'Popești-Leordeni', 'Popesti-Leordeni',
    'Chitila', 'Mogoșoaia', 'Mogosoaia', 'Otopeni', 'Dâmbovița', 'Dambovita',
    'Sighișoara', 'Sighisoara', 'Sovata', 'Reghin', 'Târnăveni', 'Tarnaveni',
]
_CITY_SET = {c.lower() for c in ROMANIAN_CITIES}


def validate_ro_locations(locations: list[str] | None) -> list[str]:
    """Filters a job's location list down to entries that are either a bare
    "românia"/"romania" or a known Romanian city, normalizing the country
    name's casing, and falls back to ``["România"]`` when nothing survives.
    Port of scraper-js's ``transformJobsForSOLR`` location step -- without
    it, any location that doesn't exactly match the allowlist (or is simply
    missing) silently uploads as-is or gets dropped instead of degrading to
    the safe generic fallback."""
    valid = []
    for loc in (locations or []):
        lower = loc.lower().strip()
        if lower in ("romania", "românia"):
            valid.append("România")
        elif lower in _CITY_SET:
            valid.append(loc)
    return valid or ["România"]


def normalize_workmode(workmode: str | None) -> str | None:
    """Port of scraper-js's ``normalizeWorkmode``."""
    if not workmode:
        return None
    lower = workmode.lower()
    if "remote" in lower:
        return "remote"
    if "office" in lower or "on-site" in lower or "site" in lower:
        return "on-site"
    return "hybrid"


def iso_z(dt: datetime) -> str:
    """UTC timestamp as ``2026-09-30T23:59:59.000Z`` -- millisecond precision,
    literal ``Z`` offset. Solr's date fields parse only this exact shape;
    Python's own ``datetime.isoformat()`` instead emits microseconds and a
    ``+00:00`` offset (e.g. ``...23:59:59.000000+00:00``), which Solr rejects
    with a 400. JS's ``Date.prototype.toISOString()`` always produces this
    shape natively, so this is what keeps the two in parity."""
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_deadline(text: str | None) -> str | None:
    """'30.09.2026' -> '2026-09-30T23:59:59.000Z' (end of the closing day).
    Also accepts an ISO date (schema.org JobPosting ``validThrough``)."""
    if not text:
        return None
    s = str(text)

    m = _DMY_RX.search(s)
    if m:
        dd, mm, yyyy = (int(x) for x in m.groups())
        try:
            return iso_z(datetime(yyyy, mm, dd, 23, 59, 59, tzinfo=timezone.utc))
        except ValueError:
            return None

    m = _ISO_RX.search(s)
    if m:
        try:
            dt = datetime.fromisoformat(m.group(0).replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:  # a bare date means UTC, not the runner's local tz
            dt = dt.replace(tzinfo=timezone.utc)
        return iso_z(dt)

    return None


def _clean_title(raw: str | None) -> str | None:
    text = text_from_html(raw) if raw and "<" in str(raw) else (str(raw).strip() if raw else None)
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()[:200]
    return text or None


def _parse_workable_json(data: dict) -> list[dict]:
    """Extract Romanian jobs from Workable widget payload."""
    items: list[dict] = []
    seen: set[str] = set()

    for job in data.get("jobs", []):
        locs = job.get("locations") if isinstance(job.get("locations"), list) else []
        ro_locs = [
            l for l in locs
            if _RO_COUNTRY_RX.search(str(l.get("countryCode") or l.get("country") or ""))
        ]
        country = str(job.get("country") or "").strip()
        is_ro = bool(_RO_COUNTRY_RX.search(country)) or len(ro_locs) > 0
        if not is_ro:
            continue

        title = _clean_title(job.get("title"))
        url = job.get("url") or job.get("shortlink") or (
            f"https://apply.workable.com/j/{job.get('shortcode')}" if job.get("shortcode") else None
        )
        if not title or not url:
            continue

        key = f"{title.lower()}|{url}"
        if key in seen:
            continue
        seen.add(key)

        items.append({
            "title": title,
            "url": url,
            "expirationdate": parse_deadline(job.get("published_on")),
        })

    return items


def parse_listing(html: str, selectors: dict | None = None) -> list[dict]:
    """Parse the open-positions page into ``{title, expirationdate, url}`` items."""
    # 1. Direct JSON from Workable widget API
    raw = html.strip() if isinstance(html, str) else ""
    if raw.startswith("{") and '"jobs"' in raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "jobs" in data:
                items = _parse_workable_json(data)
                if items:
                    log.info("parse_listing: %d items via Workable JSON API", len(items))
                    return items
        except Exception as exc:
            log.warning("Workable JSON parse error: %s", exc)

    # 2. Self-healing cascade for standard HTML (and unit test fixtures)
    sel = selectors if selectors is not None else _SEL
    articles = locate_articles(html, sel["jobArticle"])
    items: list[dict] = []
    strategies: set[str] = set()
    seen: set[str] = set()

    def _dedupe_key(title: str, url) -> str:
        return f"{title.lower()}|{url or ''}"

    if articles.mode == "jsonld":
        for posting in articles.json_ld:
            title = _clean_title(posting.get("title"))
            key = _dedupe_key(title or "", posting.get("url"))
            if not title or key in seen:
                continue
            seen.add(key)
            strategies.add("jsonld")
            items.append({
                "title": title,
                "expirationdate": parse_deadline(posting.get("validThrough")),
                "url": posting.get("url") or None,
            })
        log.info("parse_listing: %d items via JSON-LD JobPosting", len(items))
        return items

    title_primary = sel["jobTitle"][0] if isinstance(sel["jobTitle"], list) else sel["jobTitle"]
    for i, scope in enumerate(articles.scopes):
        match = first_match(
            f"title[{i}]",
            [
                ("css-cascade", lambda scope=scope: scope.text(sel["jobTitle"]).value),
                scrapling_text(scope.raw(), title_primary),
                regex_text(scope.raw(), _HN_RX),
                regex_text(scope.raw(), _A_RX),
            ],
            silent=True,
        )
        title = _clean_title(match.value)
        if not title:
            continue

        meta = scope.text(sel["jobMeta"]).value
        deadline = parse_deadline(meta) or parse_deadline(scope.full_text())
        url = scope.href(sel.get("jobUrl")).value
        key = _dedupe_key(title, url)
        if key in seen:
            continue
        seen.add(key)
        if match.strategy:
            strategies.add(match.strategy)

        items.append({"title": title, "expirationdate": deadline, "url": url})

    if items:
        tag = f" [{', '.join(sorted(strategies))}]" if strategies else ""
        log.info("parse_listing: %d items via %s%s", len(items), articles.mode, tag)
        return items

    # 3. Fallback when html is a client-rendered shell (e.g. Workable careers HTML)
    # Only triggered in production runs (selectors is None)
    if selectors is None and ("workable" in str(scraper.get("sources", {}).get("listing", "")).lower() or "workable" in raw.lower()):
        try:
            from . import fetch
            api_url = "https://apply.workable.com/api/v1/widget/accounts/logifuture?details=true"
            resp = fetch.get(api_url, label="workable widget")
            if resp.ok and resp.text.strip().startswith("{"):
                data = json.loads(resp.text)
                items = _parse_workable_json(data)
                if items:
                    log.info("parse_listing: %d items via Workable widget fallback", len(items))
                    return items
        except Exception as exc:
            log.warning("Workable widget fetch fallback error: %s", exc)

    return []
