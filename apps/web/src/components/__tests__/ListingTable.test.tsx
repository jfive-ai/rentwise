import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import { ListingTable } from "@/src/components/ListingTable";
import type { NormalizedListing } from "@/src/api/types";

jest.mock("expo-linking", () => ({ openURL: jest.fn().mockResolvedValue(undefined) }));

const stub = (id: string, price: number, beds: number, title: string): NormalizedListing => ({
  id, canonical_id: id, source: "craigslist",
  source_url: `https://example.com/${id}`, source_listing_id: id,
  title, address: null, address_normalized: null, lat: null, lon: null,
  bedrooms: beds, bathrooms: null, price_cad: price,
  pets_allowed: null, furnished: null, available_date: null,
  posted_at: "2026-05-01T00:00:00Z", last_seen_at: "2026-05-06T00:00:00Z",
  photos: [], description_snippet: null,
  school_catchments: { elementary: null, middle: null, secondary: null },
  nearest_transit: null, walkscore: null, raw_metadata: {},
});

const rows = [stub("a", 2000, 1, "A row"), stub("b", 3000, 2, "B row")];

describe("ListingTable", () => {
  it("renders one row per listing", () => {
    const { getByText } = render(
      <ListingTable listings={rows} sort="newest" onSortChange={jest.fn()} actions={{}} onAction={jest.fn()} />
    );
    expect(getByText("A row")).toBeTruthy();
    expect(getByText("B row")).toBeTruthy();
  });

  it("first click on each header picks that column's default direction", () => {
    const onSortChange = jest.fn();
    const { getByLabelText } = render(
      <ListingTable listings={rows} sort="newest" onSortChange={onSortChange} actions={{}} onAction={jest.fn()} />
    );
    fireEvent.press(getByLabelText("Sort by Title"));
    expect(onSortChange).toHaveBeenLastCalledWith("title_asc");
    fireEvent.press(getByLabelText("Sort by Price"));
    expect(onSortChange).toHaveBeenLastCalledWith("price_asc");
    fireEvent.press(getByLabelText("Sort by Beds"));
    expect(onSortChange).toHaveBeenLastCalledWith("bedrooms_desc");
    fireEvent.press(getByLabelText("Sort by Source"));
    expect(onSortChange).toHaveBeenLastCalledWith("source_asc");
  });

  it("clicking the active column toggles its direction", () => {
    const onSortChange = jest.fn();
    const { getByLabelText, rerender } = render(
      <ListingTable listings={rows} sort="price_asc" onSortChange={onSortChange} actions={{}} onAction={jest.fn()} />
    );
    fireEvent.press(getByLabelText("Sort by Price"));
    expect(onSortChange).toHaveBeenLastCalledWith("price_desc");
    rerender(
      <ListingTable listings={rows} sort="price_desc" onSortChange={onSortChange} actions={{}} onAction={jest.fn()} />
    );
    fireEvent.press(getByLabelText("Sort by Price"));
    expect(onSortChange).toHaveBeenLastCalledWith("price_asc");
  });

  it("treats the legacy 'bedrooms' alias as bedrooms_desc when toggling", () => {
    const onSortChange = jest.fn();
    const { getByLabelText } = render(
      <ListingTable listings={rows} sort="bedrooms" onSortChange={onSortChange} actions={{}} onAction={jest.fn()} />
    );
    fireEvent.press(getByLabelText("Sort by Beds"));
    expect(onSortChange).toHaveBeenLastCalledWith("bedrooms_asc");
  });

  it("renders price formatted with thousands separator", () => {
    const { getByText } = render(
      <ListingTable listings={rows} sort="newest" onSortChange={jest.fn()} actions={{}} onAction={jest.fn()} />
    );
    expect(getByText("$2,000")).toBeTruthy();
    expect(getByText("$3,000")).toBeTruthy();
  });

  it("calls onSelectListing when a row is pressed", () => {
    const onSelect = jest.fn();
    const { getByLabelText } = render(
      <ListingTable
        listings={rows}
        sort="newest"
        onSortChange={jest.fn()}
        actions={{}}
        onAction={jest.fn()}
        onSelectListing={onSelect}
      />,
    );
    fireEvent.press(getByLabelText("Select A row"));
    expect(onSelect).toHaveBeenCalledWith("a");
  });

  it("highlights the selected row via accessibilityState", () => {
    const { getByLabelText } = render(
      <ListingTable
        listings={rows}
        sort="newest"
        onSortChange={jest.fn()}
        actions={{}}
        onAction={jest.fn()}
        selectedListingId="b"
      />,
    );
    // The row with id "b" should have a non-transparent backgroundColor in
    // its computed style — selection paints surfaceAlt; unselected rows are
    // transparent. We only assert the visual difference via the style array.
    const selected = getByLabelText("Select B row");
    const unselected = getByLabelText("Select A row");
    const flatten = (s: unknown): Record<string, unknown> =>
      Array.isArray(s) ? Object.assign({}, ...s.map(flatten)) : (s as Record<string, unknown>) ?? {};
    expect(flatten(selected.props.style).backgroundColor).not.toBe("transparent");
    expect(flatten(unselected.props.style).backgroundColor).toBe("transparent");
  });
});
