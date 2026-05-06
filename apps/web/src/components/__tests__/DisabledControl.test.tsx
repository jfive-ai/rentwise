import React from "react";
import { Text } from "react-native";
import { render } from "@testing-library/react-native";
import { DisabledControl } from "@/src/components/DisabledControl";

describe("DisabledControl", () => {
  it("renders the label and phase badge", () => {
    const { getByText } = render(
      <DisabledControl label="Pets" phase="Phase 3 — more sources">
        <Text>placeholder</Text>
      </DisabledControl>
    );
    expect(getByText("Pets")).toBeTruthy();
    expect(getByText("Phase 3 — more sources")).toBeTruthy();
    expect(getByText("placeholder")).toBeTruthy();
  });

  it("marks itself accessible as disabled", () => {
    const { getByLabelText } = render(
      <DisabledControl label="Pets" phase="Phase 3">
        <Text>x</Text>
      </DisabledControl>
    );
    const node = getByLabelText("Pets, disabled (Phase 3)");
    expect(node.props.accessibilityState).toMatchObject({ disabled: true });
  });
});
