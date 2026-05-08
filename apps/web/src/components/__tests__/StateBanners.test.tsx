import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import {
  AdapterFailureBanner,
  EmptyState,
  ErrorState,
  LoadingSkeleton,
  UnsupportedFiltersBanner,
} from "@/src/components/StateBanners";
import type { AdapterHealth } from "@/src/api/types";

describe("StateBanners", () => {
  it("EmptyState renders the message", () => {
    const { getByText } = render(<EmptyState message="No matches" />);
    expect(getByText("No matches")).toBeTruthy();
  });

  it("ErrorState shows the error and calls onRetry", () => {
    const onRetry = jest.fn();
    const { getByText } = render(
      <ErrorState message="Search failed: 500" onRetry={onRetry} />
    );
    expect(getByText("Search failed: 500")).toBeTruthy();
    fireEvent.press(getByText("Retry"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("LoadingSkeleton renders the requested number of placeholders + a 'Searching…' label", () => {
    // Without the "Searching…" pill, the skeleton looked like the page was
    // broken — six static grey rows with no indication anything was in
    // flight. The visible label is part of the contract this test pins.
    const { getAllByLabelText, getByText } = render(<LoadingSkeleton rows={4} />);
    expect(getAllByLabelText("loading-row")).toHaveLength(4);
    expect(getByText(/Searching/)).toBeTruthy();
  });

  it("AdapterFailureBanner renders nothing when every source is ok", () => {
    const sourceHealth: Record<string, AdapterHealth> = {
      craigslist: {
        name: "craigslist",
        status: "ok",
        last_successful_fetch: "2026-05-08T12:00:00Z",
        last_error: null,
      },
    };
    const { toJSON } = render(<AdapterFailureBanner sourceHealth={sourceHealth} />);
    expect(toJSON()).toBeNull();
  });

  it("AdapterFailureBanner renders nothing when source_health is empty", () => {
    const { toJSON } = render(<AdapterFailureBanner sourceHealth={{}} />);
    expect(toJSON()).toBeNull();
  });

  it("AdapterFailureBanner names a single failing source and shows its first-line error", () => {
    const sourceHealth: Record<string, AdapterHealth> = {
      craigslist: {
        name: "craigslist",
        status: "degraded",
        last_successful_fetch: null,
        last_error:
          "Client error '403 Forbidden' for url 'https://vancouver.craigslist.org/...'\nFor more information check: https://developer.mozilla.org/...",
      },
    };
    const { getByText } = render(<AdapterFailureBanner sourceHealth={sourceHealth} />);
    expect(getByText("Source unavailable: craigslist")).toBeTruthy();
    // Stack-trace second-line follow-up is trimmed off — only the first
    // line of `last_error` is rendered.
    expect(getByText(/craigslist \(degraded\): Client error '403 Forbidden'/)).toBeTruthy();
  });

  it("AdapterFailureBanner pluralizes when multiple sources fail and lists each", () => {
    const sourceHealth: Record<string, AdapterHealth> = {
      craigslist: {
        name: "craigslist",
        status: "degraded",
        last_successful_fetch: null,
        last_error: "403",
      },
      rentalsca: {
        name: "rentalsca",
        status: "blocked",
        last_successful_fetch: null,
        last_error: "robots disallow",
      },
    };
    const { getByText } = render(<AdapterFailureBanner sourceHealth={sourceHealth} />);
    expect(getByText("2 sources unavailable")).toBeTruthy();
    expect(getByText(/craigslist \(degraded\)/)).toBeTruthy();
    expect(getByText(/rentalsca \(blocked\)/)).toBeTruthy();
  });

  it("UnsupportedFiltersBanner shows a comma-separated list", () => {
    const { getByText } = render(
      <UnsupportedFiltersBanner filters={["pets", "furnished"]} />
    );
    expect(getByText(/pets, furnished/)).toBeTruthy();
  });

  it("UnsupportedFiltersBanner renders nothing when list is empty", () => {
    const { toJSON } = render(<UnsupportedFiltersBanner filters={[]} />);
    expect(toJSON()).toBeNull();
  });
});
