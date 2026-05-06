import { searchClient, ApiError } from "@/src/api/client";

describe("searchClient.search", () => {
  const baseUrl = "http://api.test";
  const query = { bedrooms_min: 2, price_max: 3000 };

  beforeEach(() => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn();
  });

  it("posts to /search with the provided query and pagination", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        listings: [],
        total: 0,
        cache_status: "miss",
        unsupported_filters: [],
        source_health: {},
      }),
    });

    await searchClient(baseUrl).search({
      query: query as never,
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
      query: { bedrooms_min: 2, price_max: 3000 },
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
      json: async () => ({ detail: "bad" }),
    });

    await expect(
      searchClient(baseUrl).search({ query: {} as never })
    ).rejects.toMatchObject({ name: "ApiError", status: 422 });
  });

  it("wraps fetch network errors as ApiError(status=0)", async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new TypeError("net"));

    await expect(
      searchClient(baseUrl).search({ query: {} as never })
    ).rejects.toMatchObject({ name: "ApiError", status: 0 });
  });
});
