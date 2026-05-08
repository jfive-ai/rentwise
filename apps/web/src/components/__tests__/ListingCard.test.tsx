import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import * as Linking from "expo-linking";
import { ListingCard } from "@/src/components/ListingCard";
import type { NormalizedListing } from "@/src/api/types";

jest.mock("expo-linking", () => ({ openURL: jest.fn().mockResolvedValue(undefined) }));

const listing: NormalizedListing = {
  id: "id-1",
  canonical_id: "id-1",
  source: "craigslist",
  source_url: "https://example.com/p/123",
  source_listing_id: "123",
  title: "Sunny 2br in Kits with view",
  address: "1234 W 4th Ave",
  address_normalized: null,
  lat: null, lon: null,
  bedrooms: 2, bathrooms: 1,
  price_cad: 2800,
  pets_allowed: null, furnished: null, available_date: null,
  posted_at: "2026-05-01T10:00:00Z",
  last_seen_at: "2026-05-06T10:00:00Z",
  photos: ["https://example.com/photo.jpg"],
  description_snippet: "Top floor unit, ocean view, in-suite laundry…",
  school_catchments: { elementary: null, middle: null, secondary: null },
  nearest_transit: null, walkscore: null,
  raw_metadata: {},
};

describe("ListingCard", () => {
  it("renders title, price, beds, source badge, and snippet", () => {
    const { getByText } = render(
      <ListingCard listing={listing} actions={{}} onAction={jest.fn()} />
    );
    expect(getByText("Sunny 2br in Kits with view")).toBeTruthy();
    expect(getByText("$2,800")).toBeTruthy();
    expect(getByText("2 bd")).toBeTruthy();
    expect(getByText("craigslist")).toBeTruthy();
    expect(getByText(/Top floor unit/)).toBeTruthy();
  });

  it("renders a placeholder when there are no photos", () => {
    const { getByText } = render(
      <ListingCard listing={{ ...listing, photos: [] }} actions={{}} onAction={jest.fn()} />
    );
    expect(getByText("No photo")).toBeTruthy();
  });

  it("fires onAction with the right flag", () => {
    const onAction = jest.fn();
    const { getByLabelText } = render(
      <ListingCard listing={listing} actions={{}} onAction={onAction} />
    );
    fireEvent.press(getByLabelText("Save"));
    expect(onAction).toHaveBeenCalledWith("saved", true);
    fireEvent.press(getByLabelText("Hide"));
    expect(onAction).toHaveBeenCalledWith("hidden", true);
    fireEvent.press(getByLabelText("Contacted"));
    expect(onAction).toHaveBeenCalledWith("contacted", true);
  });

  it("toggles flag off when already on", () => {
    const onAction = jest.fn();
    const { getByLabelText } = render(
      <ListingCard listing={listing} actions={{ saved: true }} onAction={onAction} />
    );
    fireEvent.press(getByLabelText("Save"));
    expect(onAction).toHaveBeenCalledWith("saved", false);
  });

  it("opens the source URL via Linking", () => {
    const { getByLabelText } = render(
      <ListingCard listing={listing} actions={{}} onAction={jest.fn()} />
    );
    fireEvent.press(getByLabelText("Open original"));
    expect((Linking.openURL as jest.Mock)).toHaveBeenCalledWith("https://example.com/p/123");
  });

  it("shows price as '—' when null", () => {
    const { getByText } = render(
      <ListingCard listing={{ ...listing, price_cad: null }} actions={{}} onAction={jest.fn()} />
    );
    expect(getByText("—")).toBeTruthy();
  });

  it("renders 'Also on N sources' when alternates are present, expands on press", () => {
    const alt1: NormalizedListing = {
      ...listing,
      id: "id-2",
      source: "rentals_ca",
      source_url: "https://rentals.ca/p/2",
    };
    const alt2: NormalizedListing = {
      ...listing,
      id: "id-3",
      source: "padmapper",
      source_url: "https://padmapper.com/p/3",
    };
    const { getByLabelText, getByText, queryByText } = render(
      <ListingCard
        listing={listing}
        actions={{}}
        onAction={jest.fn()}
        alternates={[alt1, alt2]}
      />
    );
    expect(getByText(/Also on 2 sources/)).toBeTruthy();
    expect(queryByText("↗ rentals_ca")).toBeNull();
    fireEvent.press(getByLabelText("Show 2 duplicate sources"));
    expect(getByText("↗ rentals_ca")).toBeTruthy();
    expect(getByText("↗ padmapper")).toBeTruthy();

    fireEvent.press(getByLabelText("Open rentals_ca"));
    expect((Linking.openURL as jest.Mock)).toHaveBeenCalledWith("https://rentals.ca/p/2");
  });

  it("does not render the duplicate block when alternates is empty", () => {
    const { queryByText } = render(
      <ListingCard listing={listing} actions={{}} onAction={jest.fn()} alternates={[]} />
    );
    expect(queryByText(/Also on/)).toBeNull();
  });
});
