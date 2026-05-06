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
      json: async () => ({ ...fixture, total: 10 }),
      clone: () => ({ text: async () => JSON.stringify({ ...fixture, total: 10 }) }),
    });
    const { getByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("10 listings")).toBeTruthy());
    // Second call (Load more)
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true, status: 200,
      json: async () => ({ ...fixture, total: 10 }),
      clone: () => ({ text: async () => JSON.stringify({ ...fixture, total: 10 }) }),
    });
    fireEvent.press(getByText("Load more"));
    await waitFor(() => {
      const lastCall = (global.fetch as jest.Mock).mock.calls.at(-1)!;
      expect(JSON.parse(lastCall[1].body).offset).toBe(50);
    });
  });
});
