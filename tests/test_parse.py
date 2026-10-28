import logging
import re
from datetime import datetime, timezone

from scraper.parse import (
    iso_z,
    location_from_title,
    normalize_workmode,
    parse_deadline,
    parse_listing,
    slugify,
    validate_ro_locations,
)


def test_slugify_strips_diacritics():
    assert slugify("Key Account Manager – Vânzări Distribuitori") == "key-account-manager-vanzari-distribuitori"
    assert slugify("  Operator   exploatare și mentenanță  ") == "operator-exploatare-si-mentenanta"


def test_parse_deadline():
    assert parse_deadline("Apply by: 30.09.2026").startswith("2026-09-30T23:59:59")
    assert parse_deadline("2026-10-31").startswith("2026-10-31T00:00:00")
    assert parse_deadline("no deadline") is None
    assert parse_deadline(None) is None


# peviitor's Solr date fields parse only "...SSSZ" (millisecond precision,
# literal Z) -- the shape JS's Date.toISOString() emits natively. Python's own
# datetime.isoformat() instead emits microseconds + "+00:00", which Solr
# rejects with a 400. Both iso_z() and everything built on it must produce the
# Solr-safe shape, not Python's native one.
_ISO_Z_RX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_iso_z_matches_solr_date_format_not_pythons_native_isoformat():
    formatted = iso_z(datetime(2026, 9, 30, 23, 59, 59, 123456, tzinfo=timezone.utc))
    assert formatted == "2026-09-30T23:59:59.123Z"
    assert _ISO_Z_RX.match(formatted)


def test_parse_deadline_emits_solr_safe_z_format():
    assert _ISO_Z_RX.match(parse_deadline("Apply by: 30.09.2026"))
    assert _ISO_Z_RX.match(parse_deadline("2026-10-31"))


class TestParseListingHappyPath:
    def test_extracts_one_item_per_article(self, fixture_html, selectors):
        items = parse_listing(fixture_html("listing_ok.html"), selectors)
        assert [i["title"] for i in items] == ["Senior Widget Engineer – Platform", "Night Shift Operator"]

    def test_carries_deadline_when_present(self, fixture_html, selectors):
        items = parse_listing(fixture_html("listing_ok.html"), selectors)
        assert items[0]["expirationdate"].startswith("2026-09-30")
        assert items[1]["expirationdate"] is None

    def test_carries_the_real_scraped_url_not_a_guessed_slug(self, fixture_html, selectors):
        """The real href (which may carry an ID a title-slug guess could never
        reproduce, e.g. "/jobs/jr133930/software-architect/") must survive
        parse_listing untouched -- main.py resolves it against the listing
        page, it does not fall back to guessing when this is present."""
        items = parse_listing(fixture_html("listing_ok.html"), selectors)
        assert items[0]["url"] == "/careers/jr1/senior-widget-engineer/"
        assert items[1]["url"] == "/careers/jr2/night-shift-operator/"

    def test_empty_when_nothing_matches(self, selectors):
        assert parse_listing("<div>no jobs here</div>", selectors) == []

    def test_keeps_two_postings_sharing_a_title_but_different_urls(self, selectors):
        """Real-world case: a company reposts the same role for two locations
        ("Mecatronist" open in both Sighisoara and Sovata). Dedup must key on
        title+URL, not title alone -- this must not collapse into one job."""
        html = """
            <div class="job">
              <h2 class="job__title">Mecatronist</h2>
              <a href="https://x/mecatronist-sighisoara/">apply</a>
            </div>
            <div class="job">
              <h2 class="job__title">Mecatronist</h2>
              <a href="https://x/mecatronist-sovata/">apply</a>
            </div>
        """
        items = parse_listing(html, selectors)
        assert len(items) == 2
        assert sorted(i["url"] for i in items) == [
            "https://x/mecatronist-sighisoara/",
            "https://x/mecatronist-sovata/",
        ]

    def test_still_drops_true_duplicate_same_title_and_url(self, selectors):
        html = """
            <article class="job">
              <div class="job">
                <h2 class="job__title">Analyst</h2>
                <a href="https://x/analyst/">apply</a>
              </div>
            </article>
        """
        items = parse_listing(html, selectors)
        assert len(items) == 1

    def test_placeholder_config_does_not_crash(self):
        # default config ships  — invalid CSS, must be skipped
        result = parse_listing("<main><div class='job'><h3 class='job__title'>X</h3></div></main>")
        assert isinstance(result, list)


class TestParseListingSelfHealing:
    def test_recovers_via_fallback_class_and_fallback_heading(self, fixture_html, selectors, caplog):
        with caplog.at_level(logging.INFO):
            items = parse_listing(fixture_html("listing_renamed_class.html"), selectors)
        titles = sorted(i["title"] for i in items)
        assert titles == ["Electrical Maintenance Technician", "QA Analyst"]
        qa = next(i for i in items if i["title"] == "QA Analyst")
        assert qa["expirationdate"].startswith("2026-11-15")

    def test_falls_back_to_json_ld(self, fixture_html, selectors):
        items = parse_listing(fixture_html("listing_jsonld_only.html"), selectors)
        assert sorted(i["title"] for i in items) == ["Field Sales Representative", "Product Manager"]
        rep = next(i for i in items if i["title"] == "Field Sales Representative")
        assert rep["expirationdate"].startswith("2026-10-31")

    def test_falls_back_to_regex_article_slicing(self, fixture_html, selectors):
        items = parse_listing(fixture_html("listing_regex_article.html"), selectors)
        assert len(items) == 1
        assert items[0]["title"] == "Duty Firefighter"
        assert items[0]["expirationdate"].startswith("2026-10-20")

    def test_unrecognisable_page_returns_empty_without_raising(self, fixture_html, selectors):
        # feeds the canary in main.run()
        assert parse_listing(fixture_html("listing_unrecognisable.html"), selectors) == []


class TestLocationFromTitle:
    """Parity port of scraper-js's locationFromTitle -- a cheap location hint
    from the job title, always re-validated downstream by validate_ro_locations."""

    def test_finds_a_known_city_in_the_title(self):
        assert location_from_title("Software Engineer - Cluj", ["Default"]) == ["Cluj"]

    def test_is_case_insensitive_and_diacritic_sensitive(self):
        assert location_from_title("operator productie timisoara", ["Default"]) == ["Timisoara"]

    def test_falls_back_to_default_location_when_no_city_hint_matches(self):
        assert location_from_title("Remote DevOps Engineer", ["Default"]) == ["Default"]


class TestValidateRoLocations:
    """Parity port of scraper-js's transformJobsForSOLR location step -- the
    JS/Python gap this closes: scraper-py previously had no allowlist at all,
    so any location (or none) silently uploaded as-is instead of degrading to
    the generic "România" fallback."""

    def test_keeps_known_cities_unchanged(self):
        assert validate_ro_locations(["Sighisoara"]) == ["Sighisoara"]

    def test_normalizes_bare_country_name_casing(self):
        assert validate_ro_locations(["romania"]) == ["România"]
        assert validate_ro_locations(["românia"]) == ["România"]

    def test_drops_an_unrecognized_location_and_falls_back(self):
        assert validate_ro_locations(["Not A Real City"]) == ["România"]

    def test_falls_back_when_location_is_missing_entirely(self):
        assert validate_ro_locations(None) == ["România"]
        assert validate_ro_locations([]) == ["România"]

    def test_keeps_only_the_valid_entries_in_a_mixed_list(self):
        assert validate_ro_locations(["Sovata", "Not A City", "Sibiu"]) == ["Sovata", "Sibiu"]


class TestNormalizeWorkmode:
    """Parity port of scraper-js's normalizeWorkmode."""

    def test_maps_remote_variants(self):
        assert normalize_workmode("Full Remote") == "remote"

    def test_maps_office_or_site_variants(self):
        assert normalize_workmode("On-site") == "on-site"
        assert normalize_workmode("Office") == "on-site"

    def test_defaults_unrecognized_values_to_hybrid(self):
        assert normalize_workmode("Flexible") == "hybrid"

    def test_returns_none_for_missing_workmode(self):
        assert normalize_workmode(None) is None
        assert normalize_workmode("") is None
