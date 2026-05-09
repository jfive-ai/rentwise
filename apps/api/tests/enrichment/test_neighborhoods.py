"""NeighborhoodLookup tests against the real Vancouver Open Data file."""

from __future__ import annotations

from rentwise.enrichment.neighborhoods import NeighborhoodLookup


def test_loads_22_official_local_areas() -> None:
    nl = NeighborhoodLookup()
    assert len(nl.names) == 22
    assert "Dunbar-Southlands" in nl.names
    assert "West Point Grey" in nl.names
    assert "Kitsilano" in nl.names


def test_lookup_dunbar_address() -> None:
    """4750 W 16th Ave is the heart of Dunbar."""
    nl = NeighborhoodLookup()
    # Approximate coords for 4750 W 16th Ave (Lord Byng territory).
    assert nl.lookup(49.255, -123.185) == "Dunbar-Southlands"


def test_lookup_kitsilano_address() -> None:
    """Around 4th Ave + Vine — solidly Kitsilano."""
    nl = NeighborhoodLookup()
    assert nl.lookup(49.268, -123.165) == "Kitsilano"


def test_lookup_outside_city_is_none() -> None:
    """Burnaby coords aren't in any local area."""
    nl = NeighborhoodLookup()
    # Metrotown area
    assert nl.lookup(49.226, -122.998) is None


def test_lookup_missing_coords_is_none() -> None:
    nl = NeighborhoodLookup()
    assert nl.lookup(None, None) is None
    assert nl.lookup(49.255, None) is None
    assert nl.lookup(None, -123.185) is None


def test_resolve_aliases() -> None:
    nl = NeighborhoodLookup()
    # Dunbar → Dunbar-Southlands
    assert nl.resolve(["Dunbar"]) == ["Dunbar-Southlands"]
    # case-insensitive
    assert nl.resolve(["dunbar"]) == ["Dunbar-Southlands"]
    # Point Grey → West Point Grey
    assert nl.resolve(["Point Grey"]) == ["West Point Grey"]
    # Kits short form
    assert nl.resolve(["kits"]) == ["Kitsilano"]
    # Already-official names pass through
    assert nl.resolve(["Kitsilano"]) == ["Kitsilano"]


def test_resolve_umbrella_east_van() -> None:
    nl = NeighborhoodLookup()
    east = nl.resolve(["East Van"])
    # Umbrella expands into multiple polygons; spot-check some of them.
    assert "Grandview-Woodland" in east
    assert "Mount Pleasant" in east
    assert "Hastings-Sunrise" in east
    # West-side names should not be in the expansion.
    assert "Kitsilano" not in east
    assert "Dunbar-Southlands" not in east


def test_resolve_dedupes_preserving_order() -> None:
    nl = NeighborhoodLookup()
    # Dunbar + Southlands both alias to Dunbar-Southlands → single entry.
    assert nl.resolve(["Dunbar", "Southlands"]) == ["Dunbar-Southlands"]
    # Two unrelated names preserve order.
    assert nl.resolve(["Kits", "Point Grey"]) == ["Kitsilano", "West Point Grey"]


def test_resolve_drops_unknown_names() -> None:
    nl = NeighborhoodLookup()
    assert nl.resolve(["Atlantis"]) == []
    assert nl.resolve(["Atlantis", "Dunbar"]) == ["Dunbar-Southlands"]


def test_is_inside_any_dunbar() -> None:
    nl = NeighborhoodLookup()
    # Inside Dunbar polygon for the "Dunbar" alias.
    assert nl.is_inside_any(49.255, -123.185, ["Dunbar"]) is True
    # Kitsilano coords are not inside Dunbar.
    assert nl.is_inside_any(49.268, -123.165, ["Dunbar"]) is False


def test_is_inside_any_missing_coords_false() -> None:
    nl = NeighborhoodLookup()
    assert nl.is_inside_any(None, None, ["Dunbar"]) is False


def test_is_inside_any_no_names_false() -> None:
    nl = NeighborhoodLookup()
    assert nl.is_inside_any(49.255, -123.185, []) is False
