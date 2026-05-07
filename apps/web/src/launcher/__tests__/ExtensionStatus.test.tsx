import React from "react";
import { act, render, waitFor } from "@testing-library/react-native";
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
    const { getByText } = render(<ExtensionStatus client={client} />);
    await waitFor(() => expect(getByText("Token: short")).toBeTruthy());
  });

  it("renders the unreachable state with the error message", async () => {
    const client = makeClient({
      getCapturePair: jest.fn().mockRejectedValue(new Error("ECONNREFUSED")),
    });
    const { getByText } = render(<ExtensionStatus client={client} />);
    await waitFor(() => expect(getByText("⚠️ Capture API unreachable")).toBeTruthy());
    expect(getByText("ECONNREFUSED")).toBeTruthy();
  });

  it("stringifies non-Error rejection values", async () => {
    const client = makeClient({
      getCapturePair: jest.fn().mockRejectedValue("teapot"),
    });
    const { getByText } = render(<ExtensionStatus client={client} />);
    await waitFor(() => expect(getByText("teapot")).toBeTruthy());
  });
});
