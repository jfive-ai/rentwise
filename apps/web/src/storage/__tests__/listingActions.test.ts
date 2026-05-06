/**
 * @jest-environment jsdom
 */

import { Platform } from "react-native";

// Force the web branch so tests use window.localStorage (jsdom), not AsyncStorage.
// Platform is a plain object in react-native, so direct mutation is safe here.
// We do this before importing the module under test so the branch is resolved
// with the correct value on first import.
beforeAll(() => {
  (Platform as { OS: string }).OS = "web";
});

import {
  loadActions,
  setAction,
  clearActions,
  ListingActionMap,
} from "@/src/storage/listingActions";

describe("listingActions (web/jsdom path)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns an empty map when nothing is stored", async () => {
    const actions = await loadActions();
    expect(actions).toEqual({});
  });

  it("persists a saved action and reads it back", async () => {
    await setAction("listing-1", "saved", true);
    const actions = await loadActions();
    expect(actions["listing-1"]).toEqual({ saved: true });
  });

  it("merges multiple flags on the same listing", async () => {
    await setAction("listing-1", "saved", true);
    await setAction("listing-1", "contacted", true);
    const actions = await loadActions();
    expect(actions["listing-1"]).toEqual({ saved: true, contacted: true });
  });

  it("setAction(false) removes the flag", async () => {
    await setAction("listing-1", "saved", true);
    await setAction("listing-1", "saved", false);
    const actions = await loadActions();
    expect(actions["listing-1"]?.saved ?? false).toBe(false);
  });

  it("clearActions wipes everything", async () => {
    await setAction("a", "saved", true);
    await setAction("b", "hidden", true);
    await clearActions();
    expect(await loadActions()).toEqual({} as ListingActionMap);
  });

  it("survives a corrupted localStorage payload", async () => {
    window.localStorage.setItem("rentwise.listingActions.v1", "{not json}");
    expect(await loadActions()).toEqual({});
  });
});
