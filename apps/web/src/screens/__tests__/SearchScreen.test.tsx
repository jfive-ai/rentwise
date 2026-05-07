/**
 * @jest-environment jsdom
 */
import React from "react";
import { Platform } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { SearchScreen } from "@/src/screens/SearchScreen";
import { QueryProvider } from "@/src/state/QueryProvider";
import fixture from "@/__fixtures__/search_response.json";

beforeAll(() => {
  // Force the storage backend onto the web (localStorage) branch in tests.
  (Platform as { OS: string }).OS = "web";
  // jest-environment jsdom may not define global.fetch; seed it so spyOn works.
  if (!("fetch" in global)) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (global as any).fetch = jest.fn();
  }
});

const okResponse = () => ({
  ok: true,
  status: 200,
  json: async () => fixture,
  clone: () => ({ text: async () => JSON.stringify(fixture) }),
});

describe("SearchScreen", () => {
  beforeEach(() => {
    // Clear call history on the underlying jest.fn() (set in beforeAll). Jest's
    // restoreAllMocks resets implementations from spyOn but doesn't clear the
    // call history of a pre-existing jest.fn(); without this, mock.calls leaks
    // across tests in this suite.
    (global.fetch as jest.Mock).mockClear?.();
    jest.spyOn(global, "fetch").mockImplementation(() =>
      Promise.resolve(okResponse() as never)
    );
    window.localStorage.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  function renderScreen() {
    return render(
      <QueryProvider>
        <SearchScreen apiBaseUrl="http://api.test" />
      </QueryProvider>
    );
  }

  it("shows the empty state before any search", () => {
    const { getByText } = renderScreen();
    expect(getByText(/Set filters and press Search/i)).toBeTruthy();
  });

  it("loads results on Search and shows count + cards", async () => {
    const { getByText, findAllByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    expect((await findAllByText(/Sunny 2br|Mount Pleasant|West End|East Van|Yaletown/)).length).toBeGreaterThan(0);
  });

  it("switches to list view and renders rows", async () => {
    const { getByText, getByLabelText, findAllByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    fireEvent.press(getByLabelText("List view"));
    expect((await findAllByText("$2,800")).length).toBeGreaterThan(0);
  });

  it("renders the unsupported-filters banner when API returns non-empty list", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ ...fixture, unsupported_filters: ["pets"] }),
      clone: () => ({ text: async () => JSON.stringify({ ...fixture, unsupported_filters: ["pets"] }) }),
    });
    const { getByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText(/pets/)).toBeTruthy());
  });

  it("shows error state and Retry on non-2xx", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ error: "boom" }),
      clone: () => ({ text: async () => '{"error":"boom"}' }),
    });
    const { getByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText(/HTTP 500/)).toBeTruthy());
    expect(getByText("Retry")).toBeTruthy();
  });

  it("persists save action to local storage", async () => {
    const { getByText, findAllByLabelText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    const saveButtons = await findAllByLabelText("Save");
    fireEvent.press(saveButtons[0]);
    await waitFor(() => {
      const stored = window.localStorage.getItem("rentwise.listingActions.v1");
      expect(stored).toBeTruthy();
      const parsed = JSON.parse(stored as string);
      expect(parsed["00000000-0000-0000-0000-000000000001"]?.saved).toBe(true);
    });
  });

  it("Load more advances offset by limit", async () => {
    // First call returns total=10 so "Load more" appears
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true, status: 200,
      json: async () => ({ ...fixture, total: 20 }),
      clone: () => ({ text: async () => JSON.stringify({ ...fixture, total: 20 }) }),
    });
    const { getByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("20 listings")).toBeTruthy());
    // Second call (Load more)
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true, status: 200,
      json: async () => ({ ...fixture, total: 20 }),
      clone: () => ({ text: async () => JSON.stringify({ ...fixture, total: 20 }) }),
    });
    fireEvent.press(getByText("Load more"));
    await waitFor(() => {
      const lastCall = (global.fetch as jest.Mock).mock.calls.at(-1)!;
      expect(JSON.parse(lastCall[1].body).offset).toBe(50);
    });
  });

  it("changing sort triggers a refetch with the new sort", async () => {
    const { getByText, getByLabelText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    const callsBefore = (global.fetch as jest.Mock).mock.calls.length;

    fireEvent.press(getByLabelText("Sort by")); // newest -> price_asc

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls;
      expect(calls.length).toBe(callsBefore + 1);
      expect(JSON.parse(calls.at(-1)![1].body).sort).toBe("price_asc");
      expect(JSON.parse(calls.at(-1)![1].body).offset).toBe(0);
    });
  });

  it("does not fetch on sort change before any search has been run", () => {
    const { getByLabelText } = renderScreen();
    fireEvent.press(getByLabelText("Sort by")); // would normally refetch
    expect((global.fetch as jest.Mock).mock.calls).toHaveLength(0);
  });

  it("Retry after a failed Load more replays append=true and preserves earlier pages", async () => {
    // Initial Search: total=10, 5 listings returned (page 1)
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true, status: 200,
      json: async () => ({ ...fixture, total: 20 }),
      clone: () => ({ text: async () => JSON.stringify({ ...fixture, total: 20 }) }),
    });
    const { getByText, getAllByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("20 listings")).toBeTruthy());
    // "Sunny 2br" appears only in the first listing's title (not in any
    // FilterPanel chip), so it's a clean uniqueness probe.
    expect(getAllByText(/Sunny 2br/).length).toBe(1);

    // Successful Load more: append 5 more (10 total in DOM)
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true, status: 200,
      json: async () => ({ ...fixture, total: 20 }),
      clone: () => ({ text: async () => JSON.stringify({ ...fixture, total: 20 }) }),
    });
    fireEvent.press(getByText("Load more"));
    await waitFor(() => expect(getAllByText(/Sunny 2br/).length).toBe(2)); // duplicated by append

    // Next Load more FAILS at offset=100
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false, status: 500,
      json: async () => ({ error: "boom" }),
      clone: () => ({ text: async () => '{"error":"boom"}' }),
    });
    fireEvent.press(getByText("Load more"));
    await waitFor(() => expect(getByText("Retry")).toBeTruthy());

    // Retry succeeds — should replay append=true at offset=100, NOT replace existing 10 listings
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true, status: 200,
      json: async () => ({ ...fixture, total: 20 }),
      clone: () => ({ text: async () => JSON.stringify({ ...fixture, total: 20 }) }),
    });
    fireEvent.press(getByText("Retry"));
    await waitFor(() => {
      const lastCall = (global.fetch as jest.Mock).mock.calls.at(-1)!;
      const body = JSON.parse(lastCall[1].body);
      expect(body.offset).toBe(100); // replay the failed offset
    });
    // Earlier pages should still be in the DOM (15 total now: 10 prior + 5 new)
    await waitFor(() => expect(getAllByText(/Sunny 2br/).length).toBe(3));
  });

  it("NL mode → typing + Parse → chips appear → Search uses parsed query", async () => {
    const fetchSpy = global.fetch as jest.Mock;
    // First fetch is /translate-query (returns the parsed query).
    fetchSpy.mockImplementationOnce(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          query: {
            neighborhoods: ["Kitsilano"],
            pets: "any",
            furnished: "any",
            free_text_keywords: [],
            bedrooms_min: 2,
          },
          unsupported_filters: [],
          lang_detected: "en",
          model_used: "m",
        }),
        clone: () => ({ text: async () => "{}" }),
      } as never)
    );
    // Subsequent calls (the /search) fall through to the default beforeEach mock.

    const { getByText, getByLabelText, findByLabelText } = renderScreen();
    fireEvent.press(getByLabelText("Natural language"));
    fireEvent.changeText(getByLabelText("Search input"), "2br Kits");
    fireEvent.press(getByText("Parse"));
    // Chip rendered for the parsed neighborhood
    await findByLabelText("Remove Kitsilano");

    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    const lastSearch = (global.fetch as jest.Mock).mock.calls.find((c) =>
      (c[0] as string).endsWith("/search")
    );
    expect(lastSearch).toBeTruthy();
    expect(JSON.parse(lastSearch![1].body).query.neighborhoods).toEqual([
      "Kitsilano",
    ]);
  });

  it("rapid Search clicks: only the latest response wins", async () => {
    // First call: slow, returns total=99 (stale)
    let resolveFirst: ((v: unknown) => void) | undefined;
    const firstPromise = new Promise((resolve) => { resolveFirst = resolve; });
    const fetchSpy = global.fetch as jest.Mock;
    fetchSpy.mockReset();
    fetchSpy.mockImplementationOnce(() => firstPromise as never);
    // Second call: fast, returns total=5 (fresh, from default fixture)
    fetchSpy.mockImplementationOnce(() =>
      Promise.resolve(okResponse() as never)
    );

    const { getByText, queryByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    fireEvent.press(getByText("Search")); // overlapping click

    // Resolve the first (stale) one AFTER the second
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    resolveFirst!({
      ok: true, status: 200,
      json: async () => ({ ...fixture, total: 99 }),
      clone: () => ({ text: async () => JSON.stringify({ ...fixture, total: 99 }) }),
    });
    // Allow the now-superseded handler to run
    await new Promise((r) => setTimeout(r, 0));

    // The stale "99 listings" must NOT appear; the fresh "5 listings" stays
    expect(queryByText("99 listings")).toBeNull();
    expect(getByText("5 listings")).toBeTruthy();
  });
});
