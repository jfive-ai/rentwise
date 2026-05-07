/**
 * @jest-environment jsdom
 */
import React from "react";
import { Platform } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { SettingsScreen } from "@/src/screens/SettingsScreen";

beforeAll(() => {
  (Platform as { OS: string }).OS = "web";
  if (!("fetch" in global)) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (global as any).fetch = jest.fn();
  }
});

beforeEach(() => {
  (global.fetch as jest.Mock).mockClear?.();
});

afterEach(() => jest.restoreAllMocks());

const mockResponse = (body: unknown, ok = true, status = 200) =>
  ({
    ok,
    status,
    json: async () => body,
    clone: () => ({ text: async () => JSON.stringify(body) }),
  }) as never;

const existingSettings = {
  primary_model: "openrouter/qwen/qwen-2.5-72b-instruct:free",
  primary_api_key_masked: "sk-or-...eeff",
  fallback_model: null,
  fallback_api_key_masked: null,
  custom_base_url: null,
  timeout_seconds: 30,
};

describe("SettingsScreen", () => {
  it("loads existing settings on mount and shows the masked key", async () => {
    jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(mockResponse(existingSettings));

    const { getByText } = render(<SettingsScreen apiBaseUrl="http://api.test" />);

    await waitFor(() => expect(getByText("sk-or-...eeff")).toBeTruthy());
    expect(getByText(/Qwen 2.5 72B/)).toBeTruthy();
  });

  it("replace flow: typing a new key and Save sends it in the PUT body", async () => {
    const updated = { ...existingSettings, primary_api_key_masked: "sk-or-...new1" };
    jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(mockResponse(existingSettings))
      .mockResolvedValueOnce(mockResponse(updated));

    const { getByText, getByLabelText } = render(
      <SettingsScreen apiBaseUrl="http://api.test" />
    );

    await waitFor(() => expect(getByText("sk-or-...eeff")).toBeTruthy());

    fireEvent.press(getByText("Replace"));
    fireEvent.changeText(getByLabelText("API key"), "sk-or-newkey");
    fireEvent.press(getByText("Save"));

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls;
      const putCall = calls.find(
        (c) => (c[1] as { method: string }).method === "PUT"
      );
      expect(putCall).toBeTruthy();
    });

    const calls = (global.fetch as jest.Mock).mock.calls;
    const putCall = calls.find(
      (c) => (c[1] as { method: string }).method === "PUT"
    )!;
    expect(JSON.parse((putCall[1] as { body: string }).body)).toMatchObject({
      primary_model: "openrouter/qwen/qwen-2.5-72b-instruct:free",
      primary_api_key: "sk-or-newkey",
    });
  });

  it("test connection shows ok latency", async () => {
    jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(mockResponse(existingSettings))
      .mockResolvedValueOnce(
        mockResponse({ ok: true, error: null, latency_ms: 42, model_used: "m" })
      );

    const { getByText } = render(<SettingsScreen apiBaseUrl="http://api.test" />);

    await waitFor(() => expect(getByText("sk-or-...eeff")).toBeTruthy());

    fireEvent.press(getByText("Test connection"));

    await waitFor(() => expect(getByText(/Connection ok/i)).toBeTruthy());
    expect(getByText(/42 ms/)).toBeTruthy();
  });
});
