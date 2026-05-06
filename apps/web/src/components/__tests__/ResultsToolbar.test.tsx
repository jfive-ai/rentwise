import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import { ResultsToolbar } from "@/src/components/ResultsToolbar";

describe("ResultsToolbar", () => {
  const props = {
    total: 142,
    sort: "newest" as const,
    onSortChange: jest.fn(),
    view: "cards" as const,
    onViewChange: jest.fn(),
  };

  beforeEach(() => {
    props.onSortChange.mockReset();
    props.onViewChange.mockReset();
  });

  it("shows the total", () => {
    const { getByText } = render(<ResultsToolbar {...props} />);
    expect(getByText("142 listings")).toBeTruthy();
  });

  it("cycles sort options on press", () => {
    const { getByLabelText } = render(<ResultsToolbar {...props} />);
    fireEvent.press(getByLabelText("Sort by"));
    expect(props.onSortChange).toHaveBeenCalledWith("price_asc");
  });

  it("switches to list view on press", () => {
    const { getByLabelText } = render(<ResultsToolbar {...props} />);
    fireEvent.press(getByLabelText("List view"));
    expect(props.onViewChange).toHaveBeenCalledWith("list");
  });

  it("Map and Split buttons are disabled with a Phase 7 hint", () => {
    const { getByLabelText, getByText } = render(<ResultsToolbar {...props} />);
    const mapBtn = getByLabelText(/Map view/);
    const splitBtn = getByLabelText(/Split view/);
    expect(mapBtn.props.accessibilityState).toMatchObject({ disabled: true });
    expect(splitBtn.props.accessibilityState).toMatchObject({ disabled: true });
    fireEvent.press(mapBtn);
    expect(props.onViewChange).not.toHaveBeenCalled();
    expect(getByText(/Phase 7/i)).toBeTruthy();
  });
});
