import React from "react";
import { act, render } from "@testing-library/react-native";

jest.setTimeout(20000);
import { ExtensionStatus } from "@/src/launcher/ExtensionStatus";
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
    saveSearch: jest.fn(),
    listSavedSearches: jest.fn(),
    deleteSavedSearch: jest.fn(),
  };
  return { ...base, ...overrides };
}

describe("ExtensionStatus", () => {
  it("shows loading initially, then a paired badge with a masked token", async () => {
    let resolve: (v: { token: string; server_url: string }) => void = () => {};
    const pending = new Promise<{ token: string; server_url: string }>((r) => {
      resolve = r;
    });
    const client = makeClient({ getCapturePair: jest.fn().mockReturnValue(pending) });

    const { getByText } = render(<ExtensionStatus client={client} />);
    expect(getByText("Checking extension API…")).toBeTruthy();

    await act(async () => {
      resolve({ token: "abcdEFGH1234wxyz", server_url: "http://127.0.0.1:8000" });
      await pending;
    });

    expect(getByText("✅ Capture API ready")).toBeTruthy();
    expect(getByText(/Token: abcd…wxyz/)).toBeTruthy();
  });

  it("shows token verbatim when it is 8 chars or fewer", async () => {
    const client = makeClient({
      getCapturePair: jest
        .fn()
        .mockResolvedValue({ token: "short", server_url: "http://127.0.0.1:8000" }),
    });
    const { findByText } = render(<ExtensionStatus client={client} />);
    expect(await findByText("Token: short")).toBeTruthy();
  });

  it("renders the unreachable state with the error message", async () => {
    const client = makeClient({
      getCapturePair: jest.fn().mockRejectedValue(new Error("ECONNREFUSED")),
    });
    const { findByText, getByText } = render(<ExtensionStatus client={client} />);
    expect(await findByText("⚠️ Capture API unreachable")).toBeTruthy();
    expect(getByText("ECONNREFUSED")).toBeTruthy();
  });

  it("stringifies non-Error rejection values", async () => {
    const client = makeClient({
      getCapturePair: jest.fn().mockRejectedValue("teapot"),
    });
    const { findByText } = render(<ExtensionStatus client={client} />);
    expect(await findByText("teapot")).toBeTruthy();
  });
});
