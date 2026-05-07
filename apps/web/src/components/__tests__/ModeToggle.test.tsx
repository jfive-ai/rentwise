import React from "react";
import { Text } from "react-native";
import { fireEvent, render } from "@testing-library/react-native";
import { ModeToggle } from "@/src/components/ModeToggle";
import { QueryProvider, useQuery } from "@/src/state/QueryProvider";

function ModeProbe() {
  const { mode } = useQuery();
  return <Text testID="mode-state">{mode}</Text>;
}

function renderToggle() {
  return render(
    <QueryProvider>
      <ModeToggle />
      <ModeProbe />
    </QueryProvider>
  );
}

describe("ModeToggle", () => {
  it("pressing 'Natural language' sets mode to 'nl'", () => {
    const { getByLabelText, getByTestId } = renderToggle();
    fireEvent.press(getByLabelText("Natural language"));
    expect(getByTestId("mode-state").props.children).toBe("nl");
  });

  it("pressing 'Filters' sets mode to 'filters'", () => {
    const { getByLabelText, getByTestId } = renderToggle();
    // First flip to NL so the second press is a real change.
    fireEvent.press(getByLabelText("Natural language"));
    expect(getByTestId("mode-state").props.children).toBe("nl");
    fireEvent.press(getByLabelText("Filters"));
    expect(getByTestId("mode-state").props.children).toBe("filters");
  });
});
