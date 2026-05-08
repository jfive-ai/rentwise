import { defaultViewForWidth, isStacked, BREAKPOINTS } from "@/src/lib/responsive";

describe("defaultViewForWidth", () => {
  it("returns 'list' on phone-width viewports", () => {
    expect(defaultViewForWidth(375)).toBe("list");
    expect(defaultViewForWidth(BREAKPOINTS.narrow - 1)).toBe("list");
  });

  it("returns 'cards' on tablet/laptop widths", () => {
    expect(defaultViewForWidth(BREAKPOINTS.narrow)).toBe("cards");
    expect(defaultViewForWidth(900)).toBe("cards");
    expect(defaultViewForWidth(BREAKPOINTS.wide - 1)).toBe("cards");
  });

  it("returns 'split' on wide-desktop viewports", () => {
    expect(defaultViewForWidth(BREAKPOINTS.wide)).toBe("split");
    expect(defaultViewForWidth(1920)).toBe("split");
  });

  // jsdom default. Documented in SearchScreen tests — keep them in sync.
  it("defaults to 'cards' at the jsdom 750px viewport", () => {
    expect(defaultViewForWidth(750)).toBe("cards");
  });
});

describe("isStacked", () => {
  it("is true below the stack breakpoint and false at/above it", () => {
    expect(isStacked(BREAKPOINTS.stacked - 1)).toBe(true);
    expect(isStacked(BREAKPOINTS.stacked)).toBe(false);
    expect(isStacked(1024)).toBe(false);
  });
});
