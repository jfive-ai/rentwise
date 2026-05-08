"""Address normalizer tests — Vancouver-flavored corpus."""

from __future__ import annotations

import pytest

from rentwise.enrichment.address import (
    DIRECTIONAL,
    STREET_TYPE,
    normalize_address,
    preprocess,
)


class TestPreprocess:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Apt 5, 1234 W 4th Ave", "1234 W 4th Ave"),
            ("Unit 12, 1234 Cambie St", "1234 Cambie St"),
            ("Suite 200, 500 W Pender", "500 W Pender"),
            ("Ste 200, 500 W Pender", "500 W Pender"),
            ("#7 - 1234 Cambie St", "1234 Cambie St"),
            ("500 - 1234 West Broadway", "1234 West Broadway"),
            (
                "1234 West Broadway, Vancouver, BC V6H 1S6, Canada",
                "1234 West Broadway, Vancouver, BC V6H 1S6",
            ),
            ("  1234 W 4th Ave  ", "1234 W 4th Ave"),
        ],
    )
    def test_strips_suite_prefix_and_country(self, raw: str, expected: str) -> None:
        assert preprocess(raw) == expected

    def test_idempotent_on_clean_input(self) -> None:
        clean = "1234 W 4th Ave, Vancouver, BC"
        assert preprocess(clean) == clean
        assert preprocess(preprocess(clean)) == clean


class TestNormalizeAddress:
    def test_returns_none_for_none(self) -> None:
        assert normalize_address(None) is None

    def test_returns_none_for_blank(self) -> None:
        assert normalize_address("") is None
        assert normalize_address("   ") is None

    def test_returns_none_for_unparseable(self) -> None:
        assert normalize_address("studio in Kits, no real address") is None

    def test_canonical_form_is_lowercased(self) -> None:
        out = normalize_address("1234 W 4th Ave, Vancouver, BC V6H 1S6")
        assert out is not None
        assert out == out.lower()

    def test_directional_short_and_long_collapse(self) -> None:
        a = normalize_address("1234 W 4th Ave, Vancouver, BC V6H 1S6")
        b = normalize_address("1234 West 4th Avenue, Vancouver, BC V6H 1S6")
        assert a == b
        assert "west" in (a or "")

    def test_country_tail_does_not_change_key(self) -> None:
        a = normalize_address("1234 W 4th Ave, Vancouver, BC V6H 1S6")
        b = normalize_address("1234 W 4th Ave, Vancouver, BC V6H 1S6, Canada")
        assert a == b

    def test_suite_prefix_does_not_change_key(self) -> None:
        # The bare address must produce the same key as a suite-prefixed version.
        bare = normalize_address("1234 W 4th Ave, Vancouver, BC")
        with_apt = normalize_address("Apt 5, 1234 W 4th Ave, Vancouver, BC")
        assert bare is not None
        assert with_apt == bare

    def test_street_type_abbreviations_expand(self) -> None:
        out = normalize_address("1234 Cambie St, Vancouver, BC")
        assert out is not None
        assert "street" in out
        assert " st " not in f" {out} "

    @pytest.mark.parametrize(
        "raw",
        [
            "1234 W 4th Ave, Vancouver, BC V6H 1S6",
            "1234 Cambie St, Vancouver, BC V5Z 2X5",
            "9999 W 41st Ave, Vancouver, BC",
            "350 W Georgia St, Vancouver, BC",
        ],
    )
    def test_real_vancouver_addresses_parse(self, raw: str) -> None:
        assert normalize_address(raw) is not None


class TestLookupTables:
    def test_directionals_cover_compass(self) -> None:
        for k in ("n", "s", "e", "w", "ne", "nw", "se", "sw"):
            assert k in DIRECTIONAL

    def test_street_types_cover_common(self) -> None:
        for k in ("ave", "st", "rd", "blvd", "dr", "pl"):
            assert k in STREET_TYPE
