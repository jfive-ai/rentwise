/**
 * @jest-environment jsdom
 */
import React from "react";
import { Platform } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
// Mock expo-router before importing SearchScreen — pulling the real module
// drags in expo-asset which contains untransformed ESM and crashes the
// jest transformer. Each test can override useLocalSearchParams via the
// `mockSearchParams` helper below.
let mockSearchParams: Record<string, string | string[]> = {};
const mockReplace = jest.fn();
jest.mock("expo-router", () => ({
  router: { replace: (...args: unknown[]) => mockReplace(...args) },
  useLocalSearchParams: () => mockSearchParams,
}));

// The mock+let block above MUST precede this import so the factory captures
// the live mockSearchParams/mockReplace bindings before SearchScreen pulls
// expo-router transitively. import/first is silenced for the same reason.
// eslint-disable-next-line import/first
import { SearchScreen } from "@/src/screens/SearchScreen";
// eslint-disable-next-line import/first
import { QueryProvider } from "@/src/state/QueryProvider";
// eslint-disable-next-line import/first
import fixture from "@/__fixtures__/search_response.json";

// useViewportWidth is the only hook SearchScreen consults for layout. Mock
// it here so tests can pin a viewport size without patching react-native.
let mockedViewportWidth = 1024;
jest.mock("@/src/lib/responsive", () => {
  const actual = jest.requireActual("@/src/lib/responsive");
  return {
    ...actual,
    useViewportWidth: () => mockedViewportWidth,
  };
});

function mockViewport(width: number, _height = 800) {
  mockedViewportWidth = width;
}

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
    mockSearchParams = {};
    mockReplace.mockReset();
    // Default to a desktop width so the responsive layout (PR-C-1) renders
    // its non-stacked branch — which is what most existing tests assert on.
    // Specific tests below call mockViewport() to override.
    mockViewport(1024, 768);
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

    // Open the sort menu, then pick an option.
    fireEvent.press(getByLabelText("Sort by"));
    fireEvent.press(getByLabelText("Sort by Price ↑"));

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls;
      expect(calls.length).toBe(callsBefore + 1);
      expect(JSON.parse(calls.at(-1)![1].body).sort).toBe("price_asc");
      expect(JSON.parse(calls.at(-1)![1].body).offset).toBe(0);
    });
  });

  it("does not fetch on sort change before any search has been run", () => {
    const { getByLabelText } = renderScreen();
    // Open menu and pick an option — would normally refetch after a search.
    fireEvent.press(getByLabelText("Sort by"));
    fireEvent.press(getByLabelText("Sort by Price ↑"));
    expect((global.fetch as jest.Mock).mock.calls).toHaveLength(0);
  });

  it("Retry after a failed Load more replays append=true and preserves earlier pages", async () => {
    // Each page is a *re-keyed* copy of the fixture (unique canonical_ids
    // per call) so PR-D's cluster collapse doesn't merge them — we want
    // the DOM-count probe to reflect raw appended pages.
    const rekey = (page: number) => ({
      ...fixture,
      total: 20,
      listings: fixture.listings.map((l) => ({
        ...l,
        id: `${l.id}-p${page}`,
        canonical_id: `${l.canonical_id}-p${page}`,
      })),
    });
    const respond = (body: object) => ({
      ok: true,
      status: 200,
      json: async () => body,
      clone: () => ({ text: async () => JSON.stringify(body) }),
    });

    // Initial Search: total=20, 5 listings returned (page 1)
    (global.fetch as jest.Mock).mockResolvedValueOnce(respond(rekey(1)));
    const { getByText, getAllByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("20 listings")).toBeTruthy());
    // "Sunny 2br" appears only in the first listing's title (not in any
    // FilterPanel chip), so it's a clean uniqueness probe.
    expect(getAllByText(/Sunny 2br/).length).toBe(1);

    // Successful Load more: append 5 more (10 total in DOM)
    (global.fetch as jest.Mock).mockResolvedValueOnce(respond(rekey(2)));
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
    (global.fetch as jest.Mock).mockResolvedValueOnce(respond(rekey(3)));
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

  it("collapses listings sharing a canonical_id into one card with an alternates affordance", async () => {
    // Two listings, same canonical_id → one cluster.
    const clustered = {
      ...fixture,
      total: 2,
      listings: [
        { ...fixture.listings[0], id: "shared-a", canonical_id: "cluster-1", source: "craigslist" },
        { ...fixture.listings[0], id: "shared-b", canonical_id: "cluster-1", source: "rentals_ca" },
      ],
    };
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => clustered,
      clone: () => ({ text: async () => JSON.stringify(clustered) }),
    });

    const { getByText, getAllByText, queryByText } = renderScreen();
    fireEvent.press(getByText("Search"));

    await waitFor(() => expect(getByText("2 listings")).toBeTruthy());
    // Only one card title rendered for the cluster (not two).
    expect(getAllByText(/Sunny 2br/).length).toBe(1);
    // Affordance to expand alternates is present.
    expect(getByText(/Also on 1 source/)).toBeTruthy();
    expect(queryByText("↗ rentals_ca")).toBeNull();
  });

  it("narrow viewport: defaults view to 'list' and collapses the filter pane", async () => {
    mockViewport(375, 812);
    const { findByLabelText, getByLabelText, queryByText } = renderScreen();
    // The toggle is the only filter UI rendered while collapsed.
    const toggle = await findByLabelText("Show filters");
    expect(toggle).toBeTruthy();
    expect(toggle.props.accessibilityState).toMatchObject({ expanded: false });
    // Mode selector and Search button are NOT rendered while collapsed.
    expect(queryByText(/^Search$/)).toBeNull();
    // Tap to expand → mode/filter UI mounts.
    fireEvent.press(toggle);
    expect(getByLabelText("Hide filters").props.accessibilityState).toMatchObject({
      expanded: true,
    });
  });

  it("wide viewport: defaults view to 'split' (no toggle, filters always visible)", async () => {
    mockViewport(1440, 900);
    const { getByText, queryByLabelText, getByLabelText } = renderScreen();
    expect(queryByLabelText("Show filters")).toBeNull();
    // Toolbar's Split button is rendered active (no need for fireEvent — the
    // initial state is what we're verifying).
    expect(getByLabelText("Split view")).toBeTruthy();
    // Filters Section header is visible (Search button is part of FilterPanel)
    expect(getByText(/^Search$/)).toBeTruthy();
  });

  it("Split view renders both the map pane and the list rows", async () => {
    const { getByText, getByLabelText, findAllByText, queryByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    fireEvent.press(getByLabelText("Split view"));
    // List rows still render
    expect((await findAllByText("$2,800")).length).toBeGreaterThan(0);
    // The pre-search empty state should be gone
    expect(queryByText(/Set filters and press Search/i)).toBeNull();
  });

  it("URL params on mount: hydrates query state and auto-fires a search", async () => {
    // Simulate landing on /?bedrooms_min=2&price_max=3000&neighborhoods=Kitsilano
    mockSearchParams = {
      bedrooms_min: "2",
      price_max: "3000",
      neighborhoods: "Kitsilano",
    };
    const { getByText } = renderScreen();
    // Auto-search runs; results render without us pressing Search.
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    // Find the /search call and check its query body.
    const searchCall = (global.fetch as jest.Mock).mock.calls.find(
      (c) => (c[0] as string).endsWith("/search"),
    )!;
    expect(JSON.parse(searchCall[1].body).query).toMatchObject({
      bedrooms_min: 2,
      price_max: 3000,
      neighborhoods: ["Kitsilano"],
    });
  });

  it("Search updates the URL via history.replaceState (no expo-router unmount)", async () => {
    // We bypass expo-router's `router.replace` to update the URL because it
    // unmounts and remounts SearchScreen mid-search, which discards the
    // in-flight setState calls. Pin both behaviors in this test: URL updates
    // (history.replaceState fires) AND router.replace is NOT called.
    const replaceStateSpy = jest.spyOn(window.history, "replaceState");
    const { getByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    expect(replaceStateSpy).toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("Search button is disabled while a request is in flight", async () => {
    // Previously the suite asserted runSearch's reqIdRef race guard by
    // firing two overlapping clicks. With the new "Searching…" feedback
    // (disabled during loading), the second click can't reach the
    // handler in the first place — the protection is now *structural*.
    // Pin that behavior here.
    let resolveFirst: ((v: unknown) => void) | undefined;
    const firstPromise = new Promise((resolve) => { resolveFirst = resolve; });
    const fetchSpy = global.fetch as jest.Mock;
    fetchSpy.mockReset();
    fetchSpy.mockImplementationOnce(() => firstPromise as never);

    const { getByText, getByLabelText, queryByText } = renderScreen();
    fireEvent.press(getByText("Search"));

    // Mid-flight: button text flips to "Searching…" and is disabled.
    await waitFor(() => expect(getByLabelText("Searching…")).toBeTruthy());
    expect(queryByText("Search")).toBeNull();

    // A second click during this window must be a no-op (no second
    // /search request fires).
    fireEvent.press(getByLabelText("Searching…"));
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // Resolve the in-flight response → state transitions back to idle.
    resolveFirst!(okResponse());
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
  });
});
