from rentwise.adapters.base import AdapterCapabilities, project_query_to_capabilities
from rentwise.models import NormalizedQuery, PetPolicy


def test_project_query_drops_unsupported_fields():
    full = NormalizedQuery(
        bedrooms_min=1,
        price_max=2500,
        pets=PetPolicy.OK,  # not supported by CL
        school_catchment="Byng",  # not supported by CL
        free_text_keywords=["pool"],
    )
    caps = AdapterCapabilities(
        supported_filters={"bedrooms_min", "price_max", "free_text_keywords"}
    )
    projected, dropped = project_query_to_capabilities(full, caps)
    assert projected.bedrooms_min == 1
    assert projected.price_max == 2500
    assert projected.free_text_keywords == ["pool"]
    assert projected.pets == PetPolicy.ANY  # reset to default
    assert projected.school_catchment is None
    assert set(dropped) == {"pets", "school_catchment"}
