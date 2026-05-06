from rentwise.adapters.craigslist.neighborhoods import (
    NEIGHBORHOOD_POSTAL_SEEDS,
    normalize_neighborhood,
    seed_for,
)


def test_known_neighborhoods_have_postal_seeds():
    assert NEIGHBORHOOD_POSTAL_SEEDS["kitsilano"] == "V6K"
    assert "east vancouver" in NEIGHBORHOOD_POSTAL_SEEDS


def test_normalize_is_case_and_alias_insensitive():
    assert normalize_neighborhood("Kits") == "kitsilano"
    assert normalize_neighborhood("KITSILANO") == "kitsilano"
    assert normalize_neighborhood("east van") == "east vancouver"
    assert normalize_neighborhood("downtown") == "downtown"


def test_seed_for_unknown_returns_none():
    assert seed_for("Some Made-Up Place") is None
    assert seed_for("Kitsilano") == "V6K"
