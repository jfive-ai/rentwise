import { searchClient } from "@/src/api/client";
import { emptyQuery, type NormalizedQuery } from "@/src/api/types";

describe("searchClient.search", () => {
  const baseUrl = "http://api.test";

  beforeEach(() => {
    jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("posts to /search with the provided query and pagination", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      clone: () => ({ text: async () => "" }),
      json: async () => ({
        listings: [],
        total: 0,
        cache_status: "miss",
        unsupported_filters: [],
        source_health: {},
      }),
    });

    const query: NormalizedQuery = { ...emptyQuery(), bedrooms_min: 2, price_max: 3000 };

    await searchClient(baseUrl).search({
      query,
      limit: 25,
      offset: 0,
      sort: "newest",
      force_refresh: false,
    });

    const call = (global.fetch as jest.Mock).mock.calls[0];
    expect(call[0]).toBe("http://api.test/search");
    expect(call[1].method).toBe("POST");
    expect(call[1].headers["content-type"]).toBe("application/json");
    expect(JSON.parse(call[1].body)).toEqual({
      query: {
        bedrooms_min: 2,
        price_max: 3000,
        neighborhoods: [],
        pets: "any",
        furnished: "any",
        free_text_keywords: [],
      },
      limit: 25,
      offset: 0,
      sort: "newest",
      force_refresh: false,
    });
  });

  it("throws ApiError with status on non-2xx", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 422,
      clone: () => ({ text: async () => '{"detail":"bad"}' }),
      json: async () => ({ detail: "bad" }),
    });

    await expect(
      searchClient(baseUrl).search({ query: emptyQuery() })
    ).rejects.toMatchObject({ name: "ApiError", status: 422, payload: { detail: "bad" } });
  });

  it("wraps fetch network errors as ApiError(status=0)", async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new TypeError("net"));

    await expect(
      searchClient(baseUrl).search({ query: emptyQuery() })
    ).rejects.toMatchObject({ name: "ApiError", status: 0 });
  });
});

describe("settings", () => {
  beforeEach(() => {
    jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("getSettings returns null on 404", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "no_llm_settings" }),
      clone: () => ({ text: async () => "{}" }),
    });
    const result = await searchClient("http://api.test").getSettings();
    expect(result).toBeNull();
  });

  it("getSettings returns the masked payload on 200", async () => {
    const fixture = {
      primary_model: "openrouter/qwen/qwen-2.5-72b-instruct:free",
      primary_api_key_masked: "sk-or-...eeff",
      fallback_model: null,
      fallback_api_key_masked: null,
      custom_base_url: null,
      timeout_seconds: 30,
    };
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => fixture,
      clone: () => ({ text: async () => JSON.stringify(fixture) }),
    });
    const result = await searchClient("http://api.test").getSettings();
    expect(result?.primary_api_key_masked).toBe("sk-or-...eeff");
  });

  it("putSettings PUTs the body", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        primary_model: "m",
        primary_api_key_masked: "***",
        fallback_model: null,
        fallback_api_key_masked: null,
        custom_base_url: null,
        timeout_seconds: 30,
      }),
      clone: () => ({ text: async () => "{}" }),
    });
    (global as { fetch: unknown }).fetch = fetchMock;

    await searchClient("http://api.test").putSettings({
      primary_model: "m",
      primary_api_key: "sk-test",
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ primary_model: "m", primary_api_key: "sk-test" });
  });

  it("testConnection POSTs and returns ok/false on failure", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: false, error: "kaboom", latency_ms: 12, model_used: "m" }),
      clone: () => ({ text: async () => "{}" }),
    });
    const r = await searchClient("http://api.test").testConnection({ primary_model: "m" });
    expect(r.ok).toBe(false);
    expect(r.error).toBe("kaboom");
  });
});
