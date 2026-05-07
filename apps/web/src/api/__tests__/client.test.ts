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

describe("translateQuery", () => {
  it("POSTs to /translate-query and returns the parsed result", async () => {
    const fixture = {
      query: {
        neighborhoods: ["Kitsilano"],
        pets: "any",
        furnished: "any",
        free_text_keywords: [],
        bedrooms_min: 2,
        price_max: 3000,
      },
      unsupported_filters: [],
      lang_detected: "en",
      model_used: "openrouter/qwen/qwen-2.5-72b-instruct:free",
    };
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => fixture,
      clone: () => ({ text: async () => JSON.stringify(fixture) }),
    });
    (global as { fetch: unknown }).fetch = fetchMock;

    const client = searchClient("http://api.test/");
    const result = await client.translateQuery({ text: "2br Kits under 3000" });
    expect(result.lang_detected).toBe("en");
    expect(result.query.bedrooms_min).toBe(2);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/translate-query");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ text: "2br Kits under 3000" });
  });

  it("throws ApiError on 5xx", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({ detail: { error: "llm_transport_error", message: "down" } }),
      clone: () => ({ text: async () => '{"detail":{"error":"llm_transport_error"}}' }),
    });
    (global as { fetch: unknown }).fetch = fetchMock;

    await expect(
      searchClient("http://api.test").translateQuery({ text: "anything" })
    ).rejects.toMatchObject({ name: "ApiError", status: 502 });
  });
});
