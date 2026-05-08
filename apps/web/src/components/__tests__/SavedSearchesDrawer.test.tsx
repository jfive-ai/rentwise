import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { SavedSearchesDrawer } from "@/src/components/SavedSearchesDrawer";
import type { ApiClient } from "@/src/api/client";
import { emptyQuery, type SavedSearchResponse } from "@/src/api/types";

jest.setTimeout(20000);

function makeClient(overrides: Partial<ApiClient>): ApiClient {
  const base: ApiClient = {
    search: jest.fn(),
    translateQuery: jest.fn(),
    getSettings: jest.fn(),
    putSettings: jest.fn(),
    testConnection: jest.fn(),
    getCapturePair: jest.fn(),
    rotateCapturePair: jest.fn(),
    saveSearch: jest.fn(),
    listSavedSearches: jest.fn(),
    deleteSavedSearch: jest.fn(),
  };
  return { ...base, ...overrides };
}

const sample: SavedSearchResponse = {
  cache_key: "k1",
  query: { ...emptyQuery(), bedrooms_min: 2, neighborhoods: ["Kitsilano"] },
  label: "Kits 2br",
  alert_enabled: false,
  alert_email: null,
  cadence_minutes: 60,
  last_run_at: "2026-05-08T00:00:00Z",
  total_count: 5,
};

describe("SavedSearchesDrawer", () => {
  it("does not fetch until visible", async () => {
    const list = jest.fn().mockResolvedValue({ items: [] });
    render(
      <SavedSearchesDrawer
        visible={false}
        onClose={jest.fn()}
        client={makeClient({ listSavedSearches: list })}
        onLoad={jest.fn()}
      />,
    );
    expect(list).not.toHaveBeenCalled();
  });

  it("renders the saved-search rows when open", async () => {
    const list = jest.fn().mockResolvedValue({ items: [sample] });
    const { findByText } = render(
      <SavedSearchesDrawer
        visible={true}
        onClose={jest.fn()}
        client={makeClient({ listSavedSearches: list })}
        onLoad={jest.fn()}
      />,
    );
    expect(await findByText("Kits 2br")).toBeTruthy();
    expect(await findByText(/2\+ bd · Kitsilano/)).toBeTruthy();
  });

  it("Load fires onLoad with the saved query and closes the drawer", async () => {
    const onLoad = jest.fn();
    const onClose = jest.fn();
    const { findByLabelText } = render(
      <SavedSearchesDrawer
        visible={true}
        onClose={onClose}
        client={makeClient({
          listSavedSearches: jest.fn().mockResolvedValue({ items: [sample] }),
        })}
        onLoad={onLoad}
      />,
    );
    fireEvent.press(await findByLabelText("Load Kits 2br"));
    expect(onLoad).toHaveBeenCalledWith(sample.query);
    expect(onClose).toHaveBeenCalled();
  });

  it("Delete calls deleteSavedSearch and refreshes the list", async () => {
    const list = jest
      .fn()
      .mockResolvedValueOnce({ items: [sample] })
      .mockResolvedValueOnce({ items: [] });
    const del = jest.fn().mockResolvedValue(undefined);
    const { findByLabelText, queryByText, findByText } = render(
      <SavedSearchesDrawer
        visible={true}
        onClose={jest.fn()}
        client={makeClient({ listSavedSearches: list, deleteSavedSearch: del })}
        onLoad={jest.fn()}
      />,
    );
    expect(await findByText("Kits 2br")).toBeTruthy();
    await act(async () => {
      fireEvent.press(await findByLabelText("Delete Kits 2br"));
    });
    expect(del).toHaveBeenCalledWith("k1");
    await waitFor(() => expect(queryByText("Kits 2br")).toBeNull());
  });

  it("renders the empty-state copy when no saved searches", async () => {
    const list = jest.fn().mockResolvedValue({ items: [] });
    const { findByText } = render(
      <SavedSearchesDrawer
        visible={true}
        onClose={jest.fn()}
        client={makeClient({ listSavedSearches: list })}
        onLoad={jest.fn()}
      />,
    );
    expect(await findByText(/No saved searches yet/)).toBeTruthy();
  });

  it("renders an error message when the list fails to load", async () => {
    const list = jest.fn().mockRejectedValue(new Error("HTTP 500"));
    const { findByText } = render(
      <SavedSearchesDrawer
        visible={true}
        onClose={jest.fn()}
        client={makeClient({ listSavedSearches: list })}
        onLoad={jest.fn()}
      />,
    );
    expect(await findByText(/Couldn.+t load: HTTP 500/)).toBeTruthy();
  });
});
