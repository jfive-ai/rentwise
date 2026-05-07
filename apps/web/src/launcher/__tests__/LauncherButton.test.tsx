import React from "react";
import { Platform } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import { LauncherButton } from "@/src/launcher/LauncherButton";
import { emptyQuery, type NormalizedQuery } from "@/src/api/types";

function makeQuery(overrides: Partial<NormalizedQuery> = {}): NormalizedQuery {
  return { ...emptyQuery(), ...overrides };
}

describe("LauncherButton", () => {
  const originalOpen = window.open;
  const originalOS = Platform.OS;

  beforeEach(() => {
    Object.defineProperty(Platform, "OS", { configurable: true, value: "web" });
  });
  afterEach(() => {
    window.open = originalOpen;
    Object.defineProperty(Platform, "OS", { configurable: true, value: originalOS });
  });

  it("renders with the count of enabled sources", () => {
    const { getByText } = render(<LauncherButton query={makeQuery()} />);
    // 6 source builders are registered, each returns a URL for the empty query
    expect(getByText(/Search across sources \(6 sites\)/)).toBeTruthy();
  });

  it("opens one window.open per source on press and surfaces the success hint", async () => {
    const opened: string[] = [];
    window.open = jest.fn((url: string | URL | undefined) => {
      opened.push(String(url));
      return {} as Window; // truthy = not blocked
    }) as unknown as typeof window.open;

    const onLaunched = jest.fn();
    const { getByText } = render(
      <LauncherButton query={makeQuery({ price_max: 2500 })} onLaunched={onLaunched} />,
    );

    await act(async () => {
      fireEvent.press(getByText(/Search across sources/));
    });

    expect(opened.length).toBe(6);
    expect(onLaunched).toHaveBeenCalledTimes(1);
    expect(getByText(/Opened 6 tab\(s\)/)).toBeTruthy();
  });

  it("surfaces the popup-blocker hint when window.open returns null", async () => {
    let calls = 0;
    window.open = jest.fn(() => {
      calls += 1;
      // Block the 2nd, 4th, 6th
      return calls % 2 === 0 ? null : ({} as Window);
    }) as unknown as typeof window.open;

    const { getByText } = render(<LauncherButton query={makeQuery()} />);
    await act(async () => {
      fireEvent.press(getByText(/Search across sources/));
    });

    expect(getByText(/Popup blocker prevented 3 of 6 tab\(s\)/)).toBeTruthy();
    expect(getByText(/Allow popups for this site/)).toBeTruthy();
    // The blocked sources are the 2nd, 4th, 6th in registry order:
    // PadMapper, REW.ca, Facebook Marketplace
    expect(getByText(/PadMapper, REW\.ca, Facebook Marketplace/)).toBeTruthy();
  });

  it("on non-web platforms shows the desktop-only hint and skips window.open", async () => {
    Object.defineProperty(Platform, "OS", { configurable: true, value: "ios" });
    const open = jest.fn();
    window.open = open as unknown as typeof window.open;

    const { getByText } = render(<LauncherButton query={makeQuery()} />);
    await act(async () => {
      fireEvent.press(getByText(/Search across sources/));
    });

    expect(open).not.toHaveBeenCalled();
    expect(getByText(/needs a desktop browser/)).toBeTruthy();
  });

  it("renders per-source unsupported-filter notes when the query exceeds URL params", () => {
    const { getByText } = render(
      <LauncherButton query={makeQuery({ pets: "required", furnished: "yes" })} />,
    );
    // pets is unsupported on PadMapper / Zumper / REW.ca / FB; furnished on every source.
    expect(getByText(/PadMapper won.+t filter on: pets, furnished/)).toBeTruthy();
    expect(getByText(/Zumper won.+t filter on: pets, furnished/)).toBeTruthy();
  });
});
