import React from "react";
import { Text } from "react-native";
import { render, fireEvent } from "@testing-library/react-native";
import { QueryProvider, useQuery } from "@/src/state/QueryProvider";
import { FilterPanel } from "@/src/components/FilterPanel";

function Probe() {
  const { query } = useQuery();
  return <Text testID="query-state">{JSON.stringify(query)}</Text>;
}

function renderPanel() {
  return render(
    <QueryProvider>
      <FilterPanel onSearch={jest.fn()} />
      <Probe />
    </QueryProvider>
  );
}

describe("FilterPanel", () => {
  it("renders all five supported controls", () => {
    const { getByText, getByPlaceholderText } = renderPanel();
    expect(getByText("Bedrooms")).toBeTruthy();
    expect(getByText("Price (CAD/mo)")).toBeTruthy();
    expect(getByText("Neighborhoods")).toBeTruthy();
    expect(getByText("Keywords")).toBeTruthy();
    expect(getByPlaceholderText("Min")).toBeTruthy();
    expect(getByPlaceholderText("Max")).toBeTruthy();
  });

  it("renders disabled controls with phase badges", () => {
    const { getByText, getAllByText } = renderPanel();
    expect(getByText("School catchment")).toBeTruthy();
    expect(getByText("Pets")).toBeTruthy();
    expect(getByText("Furnished")).toBeTruthy();
    expect(getByText("Available after")).toBeTruthy();
    expect(getByText("Transit walk (max min)")).toBeTruthy();
    // multiple controls use "Phase 3"
    expect(getAllByText(/Phase 3/i).length).toBeGreaterThan(0);
  });

  it("toggles bedrooms_min / bedrooms_max via chips", () => {
    const { getByText, getByTestId } = renderPanel();
    fireEvent.press(getByText("2"));
    expect(getByTestId("query-state").props.children).toContain('"bedrooms_min":2');
  });

  it("updates price_min / price_max from numeric inputs", () => {
    const { getByPlaceholderText, getByTestId } = renderPanel();
    fireEvent.changeText(getByPlaceholderText("Min"), "1500");
    fireEvent.changeText(getByPlaceholderText("Max"), "3000");
    const state = getByTestId("query-state").props.children;
    expect(state).toContain('"price_min":1500');
    expect(state).toContain('"price_max":3000');
  });

  it("toggles neighborhoods", () => {
    const { getByText, getByTestId } = renderPanel();
    fireEvent.press(getByText("Kitsilano"));
    expect(getByTestId("query-state").props.children).toContain('"Kitsilano"');
    fireEvent.press(getByText("Kitsilano"));
    expect(getByTestId("query-state").props.children).not.toContain('"Kitsilano"');
  });

  it("adds keywords on Enter and removes them on chip press", () => {
    const { getByPlaceholderText, getByText, queryByText, getByTestId } = renderPanel();
    const input = getByPlaceholderText("Add keyword and press Enter");
    fireEvent(input, "submitEditing", { nativeEvent: { text: "balcony" } });
    expect(getByText("balcony ✕")).toBeTruthy();
    expect(getByTestId("query-state").props.children).toContain('"balcony"');
    fireEvent.press(getByText("balcony ✕"));
    expect(queryByText("balcony ✕")).toBeNull();
  });

  it("calls onSearch when Search is pressed", () => {
    const onSearch = jest.fn();
    const { getByText } = render(
      <QueryProvider>
        <FilterPanel onSearch={onSearch} />
      </QueryProvider>
    );
    fireEvent.press(getByText("Search"));
    expect(onSearch).toHaveBeenCalledTimes(1);
  });

  it("Reset clears non-default fields", () => {
    const { getByText, getByPlaceholderText, getByTestId } = renderPanel();
    fireEvent.press(getByText("2"));
    fireEvent.changeText(getByPlaceholderText("Min"), "1500");
    fireEvent.press(getByText("Reset"));
    const state = getByTestId("query-state").props.children;
    expect(state).not.toContain('"bedrooms_min":2');
    expect(state).not.toContain('"price_min":1500');
  });
});
