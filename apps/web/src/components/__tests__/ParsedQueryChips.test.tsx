import React from "react";
import { Pressable, Text } from "react-native";
import { fireEvent, render } from "@testing-library/react-native";
import { ParsedQueryChips } from "@/src/components/ParsedQueryChips";
import { QueryProvider, useQuery } from "@/src/state/QueryProvider";
import type { NormalizedQuery } from "@/src/api/types";

/**
 * Probe writes the current query to a testID node so tests can assert
 * provider state, and exposes a hidden Pressable that seeds initial
 * fields via `set()` from inside the provider (the only safe place to
 * call it). Mirrors the FilterPanel.test.tsx pattern.
 */
function Probe({ seed }: { seed?: Partial<NormalizedQuery> }) {
  const { query, set } = useQuery();
  return (
    <>
      <Text testID="query-state">{JSON.stringify(query)}</Text>
      <Pressable
        testID="seed"
        onPress={() => {
          if (seed) set(seed);
        }}
      >
        <Text>seed</Text>
      </Pressable>
    </>
  );
}

function renderChips(seed?: Partial<NormalizedQuery>) {
  const utils = render(
    <QueryProvider>
      <Probe seed={seed} />
      <ParsedQueryChips />
    </QueryProvider>
  );
  if (seed) {
    fireEvent.press(utils.getByTestId("seed"));
  }
  return utils;
}

describe("ParsedQueryChips", () => {
  it("renders empty-state copy when query has no populated fields", () => {
    const { getByText } = renderChips();
    expect(getByText(/no filters parsed/i)).toBeTruthy();
  });

  it("renders one chip per populated field", () => {
    const { getByLabelText, queryByText } = renderChips({
      bedrooms_min: 2,
      neighborhoods: ["Kitsilano"],
      pets: "ok",
    });
    // The chip's text is split across nested <Text> nodes (label + " ×"),
    // so we assert via accessibilityLabel — which the component sets per chip.
    expect(getByLabelText("Remove 2+ beds")).toBeTruthy();
    expect(getByLabelText("Remove Kitsilano")).toBeTruthy();
    expect(getByLabelText("Remove pets ok")).toBeTruthy();
    expect(queryByText(/no filters parsed/i)).toBeNull();
  });

  it("pressing a chip clears that field on the query", () => {
    const { getByLabelText, getByTestId } = renderChips({ bedrooms_min: 2 });

    // Sanity: chip rendered, query has bedrooms_min=2
    expect(getByTestId("query-state").props.children).toContain(
      '"bedrooms_min":2'
    );

    fireEvent.press(getByLabelText("Remove 2+ beds"));

    const state = JSON.parse(getByTestId("query-state").props.children);
    expect(state.bedrooms_min).toBeNull();
  });

  it("renders school catchment chip and clears it on press", () => {
    const { getByLabelText, getByTestId } = renderChips({
      school_catchment: "Lord Byng",
    });
    expect(getByLabelText("Remove Lord Byng catchment")).toBeTruthy();
    fireEvent.press(getByLabelText("Remove Lord Byng catchment"));
    const state = JSON.parse(getByTestId("query-state").props.children);
    expect(state.school_catchment).toBeNull();
  });

  it("renders transit walk chip and clears it on press", () => {
    const { getByLabelText, getByTestId } = renderChips({
      transit_max_walk_minutes: 8,
    });
    expect(getByLabelText("Remove ≤8 min walk")).toBeTruthy();
    fireEvent.press(getByLabelText("Remove ≤8 min walk"));
    const state = JSON.parse(getByTestId("query-state").props.children);
    expect(state.transit_max_walk_minutes).toBeNull();
  });
});
