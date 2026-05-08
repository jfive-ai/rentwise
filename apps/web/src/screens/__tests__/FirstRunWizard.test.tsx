/**
 * @jest-environment jsdom
 */
import React from "react";
import { Platform } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { FirstRunWizard } from "@/src/screens/FirstRunWizard";

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

describe("FirstRunWizard", () => {
  it("default provider is OpenRouter free; default model selected", () => {
    const { getByText } = render(
      <FirstRunWizard apiBaseUrl="http://api.test" onComplete={() => {}} />
    );
    expect(getByText(/OpenRouter/)).toBeTruthy();
    expect(getByText(/Qwen3 Next 80B/)).toBeTruthy();
  });

  it("ollama provider hides the API key input", () => {
    const { getByText, queryByLabelText } = render(
      <FirstRunWizard apiBaseUrl="http://api.test" onComplete={() => {}} />
    );
    fireEvent.press(getByText(/Ollama/));
    expect(queryByLabelText("API key")).toBeNull();
  });

  it("test connection success enables Finish", async () => {
    jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        mockResponse({ ok: true, error: null, latency_ms: 50, model_used: "m" })
      );
    const { getByText, getByLabelText } = render(
      <FirstRunWizard apiBaseUrl="http://api.test" onComplete={() => {}} />
    );
    fireEvent.changeText(getByLabelText("API key"), "sk-or-test");
    fireEvent.press(getByText("Test connection"));
    await waitFor(() => expect(getByText(/Connection ok/i)).toBeTruthy());
    // Finish button is shown (not the "Skip and save anyway" error-path label)
    expect(getByText("Finish")).toBeTruthy();
  });

  it("test connection failure shows error and offers Skip", async () => {
    jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        mockResponse({ ok: false, error: "bad key", latency_ms: 100, model_used: "m" })
      );
    const { getByText, getByLabelText } = render(
      <FirstRunWizard apiBaseUrl="http://api.test" onComplete={() => {}} />
    );
    fireEvent.changeText(getByLabelText("API key"), "bad");
    fireEvent.press(getByText("Test connection"));
    await waitFor(() => expect(getByText(/bad key/)).toBeTruthy());
    expect(getByText(/Skip and save anyway/i)).toBeTruthy();
  });

  it("Finish calls putSettings and onComplete", async () => {
    const onComplete = jest.fn();
    jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        mockResponse({ ok: true, error: null, latency_ms: 10, model_used: "m" })
      )
      .mockResolvedValueOnce(
        mockResponse({
          primary_model: "openrouter/qwen/qwen3-next-80b-a3b-instruct:free",
          primary_api_key_masked: "sk-or-...test",
          fallback_model: null,
          fallback_api_key_masked: null,
          custom_base_url: null,
          timeout_seconds: 30,
        })
      );
    const { getByText, getByLabelText } = render(
      <FirstRunWizard apiBaseUrl="http://api.test" onComplete={onComplete} />
    );
    fireEvent.changeText(getByLabelText("API key"), "sk-or-test");
    fireEvent.press(getByText("Test connection"));
    await waitFor(() => expect(getByText(/Connection ok/i)).toBeTruthy());
    fireEvent.press(getByText("Finish"));
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const calls = (global.fetch as jest.Mock).mock.calls;
    const putCall = calls.find((c) => (c[1] as { method: string }).method === "PUT")!;
    expect(JSON.parse((putCall[1] as { body: string }).body)).toMatchObject({
      primary_model: "openrouter/qwen/qwen3-next-80b-a3b-instruct:free",
      primary_api_key: "sk-or-test",
    });
  });
});
