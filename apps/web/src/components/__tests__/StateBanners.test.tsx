import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import { EmptyState, ErrorState, LoadingSkeleton, UnsupportedFiltersBanner } from "@/src/components/StateBanners";

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

  it("LoadingSkeleton renders the requested number of placeholders", () => {
    const { getAllByLabelText } = render(<LoadingSkeleton rows={4} />);
    expect(getAllByLabelText("loading-row")).toHaveLength(4);
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
