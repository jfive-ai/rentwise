/**
 * @jest-environment jsdom
 */

import { Platform } from "react-native";
import {
  addEntry,
  clearHistory,
  loadHistory,
  MAX_ENTRIES,
  removeEntry,
} from "@/src/storage/nlSearchHistory";

beforeAll(() => {
  (Platform as { OS: string }).OS = "web";
});

describe("nlSearchHistory (web/jsdom path)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns an empty list when nothing is stored", async () => {
    expect(await loadHistory()).toEqual([]);
  });

  it("addEntry persists and returns most-recent-first", async () => {
    await addEntry("first");
    const after = await addEntry("second");
    expect(after).toEqual(["second", "first"]);
    expect(await loadHistory()).toEqual(["second", "first"]);
  });

  it("addEntry trims whitespace and skips empty input", async () => {
    await addEntry("  hello  ");
    expect(await addEntry("   ")).toEqual(["hello"]);
    expect(await loadHistory()).toEqual(["hello"]);
  });

  it("re-adding an existing entry promotes it to the top without duplicating", async () => {
    await addEntry("a");
    await addEntry("b");
    await addEntry("c");
    const after = await addEntry("a");
    expect(after).toEqual(["a", "c", "b"]);
  });

  it(`caps history at MAX_ENTRIES (${MAX_ENTRIES})`, async () => {
    for (let i = 0; i < MAX_ENTRIES + 5; i += 1) {
      await addEntry(`q${i}`);
    }
    const list = await loadHistory();
    expect(list).toHaveLength(MAX_ENTRIES);
    // Newest first → last inserted should be at index 0.
    expect(list[0]).toBe(`q${MAX_ENTRIES + 4}`);
    // Oldest surviving entry pushed off the bottom.
    expect(list).not.toContain("q0");
  });

  it("removeEntry drops the matching entry", async () => {
    await addEntry("a");
    await addEntry("b");
    const after = await removeEntry("a");
    expect(after).toEqual(["b"]);
  });

  it("removeEntry is a no-op when the entry isn't present", async () => {
    await addEntry("a");
    const after = await removeEntry("missing");
    expect(after).toEqual(["a"]);
  });

  it("clearHistory wipes everything", async () => {
    await addEntry("a");
    await addEntry("b");
    await clearHistory();
    expect(await loadHistory()).toEqual([]);
  });

  it("survives a corrupted localStorage payload", async () => {
    window.localStorage.setItem("rentwise.nlSearchHistory.v1", "{not json");
    expect(await loadHistory()).toEqual([]);
  });

  it("ignores non-string entries inside a stored array", async () => {
    window.localStorage.setItem(
      "rentwise.nlSearchHistory.v1",
      JSON.stringify(["ok", 42, null, "  ", "  another  "]),
    );
    expect(await loadHistory()).toEqual(["ok", "another"]);
  });
});
