/** @jest-environment jsdom */
import React from "react";
import { Platform } from "react-native";
import { render } from "@testing-library/react-native";
import { MapView } from "@/src/components/MapView";
import type { NormalizedListing } from "@/src/api/types";

function listing(id: string, overrides: Partial<NormalizedListing> = {}): NormalizedListing {
  return {
    id,
    canonical_id: id,
    source: "craigslist",
    source_url: "https://example.com",
    source_listing_id: id,
    title: `Listing ${id}`,
    address: null,
    address_normalized: null,
    lat: 49.27,
    lon: -123.13,
    bedrooms: 2,
    bathrooms: null,
    price_cad: 2800,
    pets_allowed: null,
    furnished: null,
    available_date: null,
    posted_at: "2026-01-01T00:00:00Z",
    last_seen_at: "2026-01-01T00:00:00Z",
    photos: [],
    description_snippet: null,
    school_catchments: { elementary: null, middle: null, secondary: null },
    nearest_transit: null,
    walkscore: null,
    raw_metadata: {},
    ...overrides,
  };
}

describe("MapView", () => {
  const originalOS = Platform.OS;
  afterEach(() => {
    (Platform as { OS: string }).OS = originalOS;
  });

  it("renders the placeholder on native platforms", () => {
    (Platform as { OS: string }).OS = "ios";
    const { getByText } = render(
      <MapView
        listings={[listing("a")]}
        onSelectListing={jest.fn()}
        onSearchBbox={jest.fn()}
      />,
    );
    expect(getByText(/Map view is web-only/)).toBeTruthy();
  });

  it("mounts the map container on web", () => {
    (Platform as { OS: string }).OS = "web";
    const { getByTestId } = render(
      <MapView
        listings={[listing("a"), listing("b", { lat: 49.28, lon: -123.12 })]}
        onSelectListing={jest.fn()}
        onSearchBbox={jest.fn()}
      />,
    );
    expect(getByTestId("rentwise-map")).toBeTruthy();
  });

  it("renders the off-map footer when listings lack coords", () => {
    (Platform as { OS: string }).OS = "web";
    const { getByText } = render(
      <MapView
        listings={[
          listing("a"),
          listing("nogeo", { lat: null, lon: null }),
          listing("nogeo2", { lat: null, lon: null }),
        ]}
        onSelectListing={jest.fn()}
        onSearchBbox={jest.fn()}
      />,
    );
    expect(getByText(/2 listings have no location/)).toBeTruthy();
  });

  it("does not render the footer when every listing is on the map", () => {
    (Platform as { OS: string }).OS = "web";
    const { queryByText } = render(
      <MapView
        listings={[listing("a"), listing("b")]}
        onSelectListing={jest.fn()}
        onSearchBbox={jest.fn()}
      />,
    );
    expect(queryByText(/have no location/)).toBeNull();
  });
});
