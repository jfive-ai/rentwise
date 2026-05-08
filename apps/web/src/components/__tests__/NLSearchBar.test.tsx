/**
 * @jest-environment jsdom
 */
import React from "react";
import { Platform, Text } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { NLSearchBar } from "@/src/components/NLSearchBar";
import { ParsedQueryChips } from "@/src/components/ParsedQueryChips";
import { QueryProvider, useQuery } from "@/src/state/QueryProvider";

// CI's GitHub Actions Linux runners can take 6-9s for the happy-path async
// flow (changeText → re-render → press → fetch microtask → state update →
// chip render); the default 5s Jest timeout flakes. Local macOS finishes in
// ~200 ms. Bumping per-test timeout for this file specifically.
jest.setTimeout(20000);

beforeAll(() => {
  (Platform as { OS: string }).OS = "web";
  // Force jest.fn() unconditionally — modern jsdom ships native (undici) fetch
  // as a non-configurable property, so jest.spyOn(global, "fetch") fails to
  // intercept it and real network calls leak (CI: hung tests; local: same).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (global as any).fetch = jest.fn();
});

beforeEach(() => {
  (global.fetch as jest.Mock).mockReset();
  // History persists in localStorage; clear so each test starts clean and
  // the on-mount restore can't bleed a previous test's query into the input.
  window.localStorage.clear();
});

// Mode-only probe so failure-path tests can assert on mode via testID.
// The happy-path test asserts on rendered <ParsedQueryChips/> instead, since
// chip presence in the DOM is a real signal that the parse succeeded.
function ModeProbe(props: { initialMode?: "nl" | "filters" }) {
  const q = useQuery();
  const initialModeApplied = React.useRef(false);
  React.useEffect(() => {
    if (props.initialMode && !initialModeApplied.current) {
      initialModeApplied.current = true;
      if (q.mode !== props.initialMode) q.setMode(props.initialMode);
    }
  }, [props.initialMode, q]);
  return <Text testID="probe-mode">{q.mode}</Text>;
}

function renderBar(initialMode?: "nl" | "filters") {
  return render(
    <QueryProvider>
      <ModeProbe initialMode={initialMode} />
      <NLSearchBar apiBaseUrl="http://api.test" />
      <ParsedQueryChips />
    </QueryProvider>
  );
}

const mockTranslate = (body: unknown, ok = true, status = 200) => {
  (global.fetch as jest.Mock).mockResolvedValue({
    ok,
    status,
    json: async () => body,
    clone: () => ({ text: async () => JSON.stringify(body) }),
  });
};

describe("NLSearchBar", () => {
  it("submits text to /translate-query and updates the query", async () => {
    mockTranslate({
      query: {
        neighborhoods: ["Kitsilano"],
        pets: "any",
        furnished: "any",
        free_text_keywords: [],
        bedrooms_min: 2,
        price_max: 3000,
      },
      unsupported_filters: [],
      lang_detected: "en",
      model_used: "m",
    });
    const { getByLabelText, getByText, findByLabelText } = renderBar();
    fireEvent.changeText(getByLabelText("Search input"), "2br Kits under 3000");
    fireEvent.press(getByText("Parse"));
    // Chips appearing in the DOM = parse succeeded + state updated + reconciled.
    await findByLabelText("Remove 2+ beds");
    await findByLabelText("Remove Kitsilano");
  });

  it("surfaces the server error detail on 5xx and stays in NL mode", async () => {
    mockTranslate(
      {
        detail: {
          error: "llm_transport_error",
          message:
            "All LLM providers failed; last error: OpenRouter 401 No cookie auth credentials",
        },
      },
      false,
      502
    );
    const { getByLabelText, getByText, getByTestId, findByText } = renderBar("nl");
    fireEvent.changeText(getByLabelText("Search input"), "anything");
    fireEvent.press(getByText("Parse"));
    await findByText(/All LLM providers failed/);
    // Mode stays in NL — the user opted into NL and we don't yank them out.
    expect(getByTestId("probe-mode").props.children).toBe("nl");
    // But a recovery action is offered.
    expect(getByText("Use filter mode")).toBeTruthy();
  });

  it("surfaces the network error message on transport failure", async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new TypeError("Network down"));
    const { getByLabelText, getByText, getByTestId, findByText } = renderBar("nl");
    fireEvent.changeText(getByLabelText("Search input"), "anything");
    fireEvent.press(getByText("Parse"));
    await findByText(/Network down/);
    expect(getByTestId("probe-mode").props.children).toBe("nl");
  });

  it('"Use filter mode" recovery action flips mode and clears the error', async () => {
    mockTranslate({ detail: { message: "LLM down" } }, false, 502);
    const { getByLabelText, getByText, getByTestId, findByText, queryByText } = renderBar("nl");
    fireEvent.changeText(getByLabelText("Search input"), "anything");
    fireEvent.press(getByText("Parse"));
    await findByText(/LLM down/);
    fireEvent.press(getByText("Use filter mode"));
    await waitFor(() =>
      expect(getByTestId("probe-mode").props.children).toBe("filters")
    );
    expect(queryByText(/LLM down/)).toBeNull();
  });

  it("appends successful parses to recent searches and supports remove + clear", async () => {
    mockTranslate({
      query: {
        neighborhoods: ["Kitsilano"],
        pets: "any",
        furnished: "any",
        free_text_keywords: [],
        bedrooms_min: 2,
        price_max: 3000,
      },
      unsupported_filters: [],
      lang_detected: "en",
      model_used: "m",
    });
    const { getByLabelText, getByText, findByLabelText, queryByLabelText } =
      renderBar();
    fireEvent.changeText(getByLabelText("Search input"), "2br Kits under 3000");
    fireEvent.press(getByText("Parse"));
    // Wait for history toggle to appear (i.e. the parse succeeded + persisted).
    const toggle = await findByLabelText("Show recent searches");
    fireEvent.press(toggle);
    // Row exposes both pick + remove affordances.
    await findByLabelText("Use search: 2br Kits under 3000");
    fireEvent.press(getByLabelText("Remove search: 2br Kits under 3000"));
    await waitFor(() =>
      expect(
        queryByLabelText("Use search: 2br Kits under 3000"),
      ).toBeNull(),
    );
    // Empty list collapses the whole panel — the toggle disappears too.
    await waitFor(() => {
      expect(queryByLabelText("Show recent searches")).toBeNull();
      expect(queryByLabelText("Hide recent searches")).toBeNull();
    });
  });

  it("does not record history on a failed parse", async () => {
    mockTranslate({ detail: { message: "LLM down" } }, false, 502);
    const { getByLabelText, getByText, findByText, queryByLabelText } =
      renderBar("nl");
    fireEvent.changeText(getByLabelText("Search input"), "anything");
    fireEvent.press(getByText("Parse"));
    await findByText(/LLM down/);
    expect(queryByLabelText("Show recent searches")).toBeNull();
  });

  it("restores the most recent query into the input on mount", async () => {
    window.localStorage.setItem(
      "rentwise.nlSearchHistory.v1",
      JSON.stringify(["latest one", "older one"]),
    );
    const { findByDisplayValue } = renderBar();
    await findByDisplayValue("latest one");
  });

  it("mount restore does not clobber text the user already typed", async () => {
    // Pre-seed history so the restore path *would* fire if not guarded.
    window.localStorage.setItem(
      "rentwise.nlSearchHistory.v1",
      JSON.stringify(["restored value"]),
    );
    const { getByLabelText, findByLabelText, queryByDisplayValue } = renderBar();
    // Type synchronously, before loadHistory()'s .then() microtask drains.
    // Without the nlTextRef guard, the captured-empty closure would overwrite
    // this value with "restored value".
    fireEvent.changeText(getByLabelText("Search input"), "user typed first");
    // Wait until the history panel renders — signals the restore effect ran.
    await findByLabelText("Show recent searches");
    expect(
      (getByLabelText("Search input") as unknown as { props: { value: string } })
        .props.value,
    ).toBe("user typed first");
    expect(queryByDisplayValue("restored value")).toBeNull();
  });

  it("Clear all wipes the recent-searches list", async () => {
    window.localStorage.setItem(
      "rentwise.nlSearchHistory.v1",
      JSON.stringify(["a query", "another"]),
    );
    const { findByLabelText, getByLabelText, queryByLabelText } = renderBar();
    const toggle = await findByLabelText("Show recent searches");
    fireEvent.press(toggle);
    fireEvent.press(getByLabelText("Clear all recent searches"));
    await waitFor(() => {
      expect(queryByLabelText("Use search: a query")).toBeNull();
      expect(queryByLabelText("Show recent searches")).toBeNull();
    });
  });

  it("disables Parse while a request is in flight", async () => {
    let resolveFetch: ((v: unknown) => void) | undefined;
    const pending = new Promise((r) => {
      resolveFetch = r;
    });
    (global.fetch as jest.Mock).mockImplementation(() => pending);
    const { getByLabelText, getByText } = renderBar();
    fireEvent.changeText(getByLabelText("Search input"), "1br anywhere");
    fireEvent.press(getByText("Parse"));
    expect(getByText(/Parsing/i)).toBeTruthy();
    resolveFetch!({
      ok: true,
      status: 200,
      json: async () => ({
        query: {
          neighborhoods: [],
          pets: "any",
          furnished: "any",
          free_text_keywords: [],
          bedrooms_min: 1,
        },
        unsupported_filters: [],
        lang_detected: "en",
        model_used: "m",
      }),
      clone: () => ({ text: async () => "{}" }),
    });
    await waitFor(() => expect(getByText("Parse")).toBeTruthy());
  });
});
