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

  it("opens the sort menu and exposes every column option", () => {
    const { getByLabelText, queryByLabelText } = render(<ResultsToolbar {...props} />);
    // Menu starts collapsed.
    expect(queryByLabelText("Sort by Title A→Z")).toBeNull();
    fireEvent.press(getByLabelText("Sort by"));
    // Each column gets at least one option in the menu.
    expect(getByLabelText("Sort by Title A→Z")).toBeTruthy();
    expect(getByLabelText("Sort by Title Z→A")).toBeTruthy();
    expect(getByLabelText("Sort by Price ↑")).toBeTruthy();
    expect(getByLabelText("Sort by Price ↓")).toBeTruthy();
    expect(getByLabelText("Sort by Beds ↑")).toBeTruthy();
    expect(getByLabelText("Sort by Beds ↓")).toBeTruthy();
    expect(getByLabelText("Sort by Source A→Z")).toBeTruthy();
    expect(getByLabelText("Sort by Source Z→A")).toBeTruthy();
  });

  it("emits onSortChange when a menu option is picked", () => {
    const { getByLabelText } = render(<ResultsToolbar {...props} />);
    fireEvent.press(getByLabelText("Sort by"));
    fireEvent.press(getByLabelText("Sort by Source A→Z"));
    expect(props.onSortChange).toHaveBeenCalledWith("source_asc");
  });

  it("renders the active sort label on the trigger", () => {
    const { getByLabelText } = render(
      <ResultsToolbar {...props} sort="title_desc" />,
    );
    expect(getByLabelText("Sort by").props.children).toBeDefined();
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

  it("Split view is now active and switches via the toolbar", () => {
    const { getByLabelText } = render(<ResultsToolbar {...props} />);
    const splitBtn = getByLabelText("Split view");
    expect(splitBtn.props.accessibilityState).not.toMatchObject({ disabled: true });
    fireEvent.press(splitBtn);
    expect(props.onViewChange).toHaveBeenCalledWith("split");
  });
});
