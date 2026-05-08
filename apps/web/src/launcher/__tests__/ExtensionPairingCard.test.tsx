import React from "react";
import { Platform } from "react-native";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { ExtensionPairingCard } from "@/src/launcher/ExtensionPairingCard";
import type { ApiClient } from "@/src/api/client";

// React Native test renderer's first cold render in a suite can be slow on
// CI runners; bump the per-test timeout so async finders don't trip.
jest.setTimeout(20000);

function makeClient(overrides: Partial<ApiClient>): ApiClient {
  const base: ApiClient = {
    search: jest.fn(),
    translateQuery: jest.fn(),
    getSettings: jest.fn(),
    putSettings: jest.fn(),
    testConnection: jest.fn(),
    getCapturePair: jest.fn(),
    rotateCapturePair: jest.fn(),
    saveSearch: jest.fn(),
    listSavedSearches: jest.fn(),
    deleteSavedSearch: jest.fn(),
    getWebPushPublicKey: jest.fn(),
    subscribeWebPush: jest.fn(),
    unsubscribeWebPush: jest.fn(),
  };
  return { ...base, ...overrides };
}

describe("ExtensionPairingCard", () => {
  const apiBaseUrl = "http://127.0.0.1:8000";

  it("renders the loading state, then surfaces the pairing values", async () => {
    const client = makeClient({
      getCapturePair: jest
        .fn()
        .mockResolvedValue({ token: "abcdEFGH1234wxyz", server_url: apiBaseUrl }),
    });
    const { findByText, getAllByText, getByText } = render(
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
    );
    expect(getByText("Loading pairing…")).toBeTruthy();

    // findByText polls until the masked token shows up, which only happens
    // after the async pairing fetch resolves and the component re-renders.
    expect(await findByText(/abcd•+wxyz/)).toBeTruthy();

    expect(getByText("API URL")).toBeTruthy();
    expect(getByText("Pairing token")).toBeTruthy();
    // The URL appears in both the field value row and the "Tip:" footer.
    expect(getAllByText(apiBaseUrl).length).toBeGreaterThanOrEqual(1);
  });

  it("toggles token visibility when Reveal is pressed", async () => {
    const client = makeClient({
      getCapturePair: jest
        .fn()
        .mockResolvedValue({ token: "abcdEFGH1234wxyz", server_url: apiBaseUrl }),
    });
    const { findByText, getByText, getAllByRole } = render(
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
    );
    await findByText(/abcd•+wxyz/);

    const revealBtn = getByText("Reveal");
    fireEvent.press(revealBtn);
    expect(getByText("abcdEFGH1234wxyz")).toBeTruthy();
    expect(getByText("Hide")).toBeTruthy();
    // Smoke check the role lookup so we know the buttons render correctly.
    expect(getAllByRole("button").length).toBeGreaterThan(0);
  });

  it("shows the error state when the initial fetch rejects", async () => {
    const client = makeClient({
      getCapturePair: jest.fn().mockRejectedValue(new Error("connect EHOSTUNREACH")),
    });
    const { findByText } = render(
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
    );
    expect(await findByText(/Couldn.+t load pairing: connect EHOSTUNREACH/)).toBeTruthy();
  });

  it("rotate replaces the displayed token and reveals the new value", async () => {
    const client = makeClient({
      getCapturePair: jest
        .fn()
        .mockResolvedValue({ token: "OLDtoken1111oooo", server_url: apiBaseUrl }),
      rotateCapturePair: jest
        .fn()
        .mockResolvedValue({ token: "NEWtoken9999nnnn", server_url: apiBaseUrl }),
    });
    const { findByText, getByText } = render(
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
    );
    await findByText(/OLDt•+oooo/);

    const rotateBtn = getByText("Rotate token");
    await act(async () => {
      fireEvent.press(rotateBtn);
    });

    // After rotate the token is revealed verbatim per spec § 6.2 rationale
    expect(getByText("NEWtoken9999nnnn")).toBeTruthy();
    expect(client.rotateCapturePair).toHaveBeenCalledTimes(1);
  });

  it("rotate failure flips the card into the error state", async () => {
    const client = makeClient({
      getCapturePair: jest
        .fn()
        .mockResolvedValue({ token: "abcdEFGH1234wxyz", server_url: apiBaseUrl }),
      rotateCapturePair: jest.fn().mockRejectedValue(new Error("rotate failed")),
    });
    const { findByText, getByText } = render(
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
    );
    await findByText(/abcd•+wxyz/);

    await act(async () => {
      fireEvent.press(getByText("Rotate token"));
    });
    await waitFor(() =>
      expect(getByText(/Couldn.+t load pairing: rotate failed/)).toBeTruthy(),
    );
  });

  it("shows a copy hint when navigator.clipboard is unavailable on native", async () => {
    const originalOS = Platform.OS;
    Object.defineProperty(Platform, "OS", { configurable: true, value: "ios" });
    try {
      const client = makeClient({
        getCapturePair: jest
          .fn()
          .mockResolvedValue({ token: "abcdEFGH1234wxyz", server_url: apiBaseUrl }),
      });
      const { findByText, getAllByText, getByText } = render(
        <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
      );
      await findByText("API URL");
      const copyBtns = getAllByText("Copy");
      await act(async () => {
        fireEvent.press(copyBtns[0]!);
      });
      expect(getByText(/copy is only available in the web app/)).toBeTruthy();
    } finally {
      Object.defineProperty(Platform, "OS", { configurable: true, value: originalOS });
    }
  });
});
