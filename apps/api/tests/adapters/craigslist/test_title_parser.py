import pytest

from rentwise.adapters.craigslist.title_parser import parse_title


@pytest.mark.parametrize(
    "title,price,beds,sqft,hint",
    [
        ("$2500 / 2br - 950ft² - Bright apt (kitsilano)", 2500, 2.0, 950, "kitsilano"),
        ("$1800 / 1br - cozy in the heart of east van", 1800, 1.0, None, "east van"),
        ("$3200 / studio - 600ft2 - downtown loft (yaletown)", 3200, 0.5, 600, "yaletown"),
        ("$4000 / 3br - 1200ft² - Sunny home (Point Grey/UBC)", 4000, 3.0, 1200, "point grey"),
        ("garage sale today only", None, None, None, None),
        ("$ - missing price", None, None, None, None),
    ],
)
def test_parse_title_extracts(title, price, beds, sqft, hint):
    r = parse_title(title)
    assert r.price_cad == price
    assert r.bedrooms == beds
    assert r.sqft == sqft
    assert r.neighborhood_hint == hint


def test_parse_title_never_raises_on_unicode():
    parse_title("$2500 / 2베드 - 키츠 (kitsilano) 🏠")
    parse_title("")
    parse_title("\x00\x01\x02")
