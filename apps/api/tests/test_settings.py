from rentwise.settings import Settings


def test_settings_phase1_defaults():
    s = Settings()
    assert s.search_cache_ttl_seconds == 900
    assert s.search_page_default == 50
    assert s.search_page_max == 200
    assert s.craigslist_region == "vancouver"


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("RENTWISE_SEARCH_CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("RENTWISE_CRAIGSLIST_REGION", "seattle")
    s = Settings()
    assert s.search_cache_ttl_seconds == 60
    assert s.craigslist_region == "seattle"
