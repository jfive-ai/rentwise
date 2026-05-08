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

  it("Map view is now active and switches via the toolbar", () => {
    const { getByLabelText } = render(<ResultsToolbar {...props} />);
    const mapBtn = getByLabelText("Map view");
    expect(mapBtn.props.accessibilityState).not.toMatchObject({ disabled: true });
    fireEvent.press(mapBtn);
    expect(props.onViewChange).toHaveBeenCalledWith("map");
  });

  it("Split is still flagged as Phase 7 PR-B placeholder", () => {
    const { getByLabelText } = render(<ResultsToolbar {...props} />);
    const splitBtn = getByLabelText(/Split view/);
    expect(splitBtn.props.accessibilityState).toMatchObject({ disabled: true });
    fireEvent.press(splitBtn);
    expect(props.onViewChange).not.toHaveBeenCalled();
  });
});
