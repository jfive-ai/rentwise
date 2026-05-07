/**
 * @jest-environment jsdom
 */
import React from "react";
import { Platform } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { NLSearchBar } from "@/src/components/NLSearchBar";
import { QueryProvider, useQuery } from "@/src/state/QueryProvider";

beforeAll(() => {
  (Platform as { OS: string }).OS = "web";
  if (!("fetch" in global)) {
    (global as { fetch: unknown }).fetch = jest.fn();
  }
});

beforeEach(() => {
  (global.fetch as jest.Mock).mockClear?.();
});

afterEach(() => {
  jest.restoreAllMocks();
});

function Probe(props: {
  onReady: (q: ReturnType<typeof useQuery>) => void;
  initialMode?: "nl" | "filters";
}) {
  const q = useQuery();
  const initialModeApplied = React.useRef(false);
  React.useEffect(() => {
    // Apply the requested initial mode exactly once so the fallback path
    // can flip back to "filters" without the probe immediately re-flipping
    // it to "nl" again.
    if (props.initialMode && !initialModeApplied.current) {
      initialModeApplied.current = true;
      if (q.mode !== props.initialMode) q.setMode(props.initialMode);
    }
    props.onReady(q);
  }, [q, props]);
  return null;
}

function renderBar(
  probe?: (q: ReturnType<typeof useQuery>) => void,
  initialMode?: "nl" | "filters"
) {
  return render(
    <QueryProvider>
      {probe ? <Probe onReady={probe} initialMode={initialMode} /> : null}
      <NLSearchBar apiBaseUrl="http://api.test" />
    </QueryProvider>
  );
}

const mockTranslate = (body: unknown, ok = true, status = 200) => {
  jest.spyOn(global, "fetch").mockResolvedValue({
    ok,
    status,
    json: async () => body,
    clone: () => ({ text: async () => JSON.stringify(body) }),
  } as never);
};

describe("NLSearchBar", () => {
  it("submits text to /translate-query and updates the query", async () => {
    let captured: ReturnType<typeof useQuery> | null = null;
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
    const { getByLabelText, getByText } = renderBar((q) => {
      captured = q;
    });
    fireEvent.changeText(getByLabelText("Search input"), "2br Kits under 3000");
    fireEvent.press(getByText("Parse"));
    await waitFor(() => expect(captured!.query.bedrooms_min).toBe(2));
    expect(captured!.query.neighborhoods).toEqual(["Kitsilano"]);
  });

  it("falls back to filter mode on 5xx", async () => {
    let captured: ReturnType<typeof useQuery> | null = null;
    mockTranslate({ detail: { error: "llm_transport_error" } }, false, 502);
    // Start in NL mode (one-shot) so the fallback can flip back to filters.
    const { getByLabelText, getByText, findByText } = renderBar(
      (q) => {
        captured = q;
      },
      "nl"
    );
    fireEvent.changeText(getByLabelText("Search input"), "anything");
    fireEvent.press(getByText("Parse"));
    await findByText(/LLM unavailable/i);
    await waitFor(() => expect(captured!.mode).toBe("filters"));
  });

  it("falls back on network error", async () => {
    let captured: ReturnType<typeof useQuery> | null = null;
    jest.spyOn(global, "fetch").mockRejectedValue(new TypeError("Network down"));
    const { getByLabelText, getByText, findByText } = renderBar(
      (q) => {
        captured = q;
      },
      "nl"
    );
    fireEvent.changeText(getByLabelText("Search input"), "anything");
    fireEvent.press(getByText("Parse"));
    await findByText(/LLM unavailable/i);
    await waitFor(() => expect(captured!.mode).toBe("filters"));
  });

  it("disables Parse while a request is in flight", async () => {
    let resolveFetch: ((v: unknown) => void) | undefined;
    const pending = new Promise((r) => {
      resolveFetch = r;
    });
    jest.spyOn(global, "fetch").mockImplementation(() => pending as never);
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
