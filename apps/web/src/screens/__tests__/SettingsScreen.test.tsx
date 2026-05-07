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

const stubCapturePair = {
  token: "abcdef0123456789abcdef0123456789",
  server_url: "http://api.test",
};

/**
 * URL-dispatching fetch mock. SettingsScreen now also mounts
 * ExtensionPairingCard, which fires its own GET /capture/pair on
 * mount; so a strict `mockResolvedValueOnce` chain by call order
 * gets brittle. The dispatcher answers /capture/pair with a stub and
 * lets each test inject overrides for the specific endpoint(s) it
 * cares about.
 */
function setupFetchMock(
  overrides: Partial<{
    settings: unknown;
    putSettings: unknown;
    test: unknown;
  }> = {},
): jest.Mock {
  const mock = jest.fn(async (input: string, init?: { method?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/capture/pair") && method === "GET") {
      return mockResponse(stubCapturePair);
    }
    if (url.endsWith("/settings/llm") && method === "GET") {
      return mockResponse(overrides.settings ?? existingSettings);
    }
    if (url.endsWith("/settings/llm") && method === "PUT") {
      return mockResponse(overrides.putSettings ?? existingSettings);
    }
    if (url.endsWith("/settings/llm/test") && method === "POST") {
      return mockResponse(
        overrides.test ?? {
          ok: true,
          error: null,
          latency_ms: 42,
          model_used: "m",
        },
      );
    }
    throw new Error(`unmocked fetch: ${method} ${url}`);
  });
  jest.spyOn(global, "fetch").mockImplementation(mock as never);
  return mock;
}

describe("SettingsScreen", () => {
  it("loads existing settings on mount and shows the masked key", async () => {
    setupFetchMock();

    const { getByText } = render(<SettingsScreen apiBaseUrl="http://api.test" />);

    await waitFor(() => expect(getByText("sk-or-...eeff")).toBeTruthy());
    expect(getByText(/Qwen 2.5 72B/)).toBeTruthy();
  });

  it("replace flow: typing a new key and Save sends it in the PUT body", async () => {
    const updated = { ...existingSettings, primary_api_key_masked: "sk-or-...new1" };
    const mock = setupFetchMock({ putSettings: updated });

    const { getByText, getByLabelText } = render(
      <SettingsScreen apiBaseUrl="http://api.test" />
    );

    await waitFor(() => expect(getByText("sk-or-...eeff")).toBeTruthy());

    fireEvent.press(getByText("Replace"));
    fireEvent.changeText(getByLabelText("API key"), "sk-or-newkey");
    fireEvent.press(getByText("Save"));

    await waitFor(() => {
      const putCall = mock.mock.calls.find(
        (c) => (c[1] as { method: string }).method === "PUT"
      );
      expect(putCall).toBeTruthy();
    });

    const putCall = mock.mock.calls.find(
      (c) => (c[1] as { method: string }).method === "PUT"
    )!;
    expect(JSON.parse((putCall[1] as { body: string }).body)).toMatchObject({
      primary_model: "openrouter/qwen/qwen-2.5-72b-instruct:free",
      primary_api_key: "sk-or-newkey",
    });
  });

  it("test connection shows ok latency", async () => {
    setupFetchMock();

    const { getByText } = render(<SettingsScreen apiBaseUrl="http://api.test" />);

    await waitFor(() => expect(getByText("sk-or-...eeff")).toBeTruthy());

    fireEvent.press(getByText("Test connection"));

    await waitFor(() => expect(getByText(/Connection ok/i)).toBeTruthy());
    expect(getByText(/42 ms/)).toBeTruthy();
  });
});
