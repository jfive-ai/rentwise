import React from "react";
import { Platform } from "react-native";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { ExtensionPairingCard } from "@/src/launcher/ExtensionPairingCard";
import type { ApiClient } from "@/src/api/client";

function makeClient(overrides: Partial<ApiClient>): ApiClient {
  const base: ApiClient = {
    search: jest.fn(),
    translateQuery: jest.fn(),
    getSettings: jest.fn(),
    putSettings: jest.fn(),
    testConnection: jest.fn(),
    getCapturePair: jest.fn(),
    rotateCapturePair: jest.fn(),
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
    const { getAllByText, getByText, queryByText } = render(
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
    );
    expect(getByText("Loading pairing…")).toBeTruthy();
    await waitFor(() => expect(queryByText("Loading pairing…")).toBeNull());

    expect(getByText("API URL")).toBeTruthy();
    expect(getByText("Pairing token")).toBeTruthy();
    // The URL appears in both the field value row and the "Tip:" footer.
    expect(getAllByText(apiBaseUrl).length).toBeGreaterThanOrEqual(1);
    // token is masked by default
    expect(getByText(/abcd•+wxyz/)).toBeTruthy();
  });

  it("toggles token visibility when Reveal is pressed", async () => {
    const client = makeClient({
      getCapturePair: jest
        .fn()
        .mockResolvedValue({ token: "abcdEFGH1234wxyz", server_url: apiBaseUrl }),
    });
    const { getByText, getAllByRole } = render(
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
    );
    await waitFor(() => expect(getByText(/abcd•+wxyz/)).toBeTruthy());

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
    const { getByText } = render(
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
    );
    await waitFor(() =>
      expect(getByText(/Couldn.+t load pairing: connect EHOSTUNREACH/)).toBeTruthy(),
    );
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
    const { getByText } = render(
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
    );
    await waitFor(() => expect(getByText(/OLDt•+oooo/)).toBeTruthy());

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
    const { getByText } = render(
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
    );
    await waitFor(() => expect(getByText(/abcd•+wxyz/)).toBeTruthy());

    await act(async () => {
      fireEvent.press(getByText("Rotate token"));
    });
    expect(getByText(/Couldn.+t load pairing: rotate failed/)).toBeTruthy();
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
      const { getAllByText, getByText } = render(
        <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />,
      );
      await waitFor(() => expect(getByText("API URL")).toBeTruthy());
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
