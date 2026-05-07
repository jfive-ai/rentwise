/**
 * @jest-environment jsdom
 */
import React from "react";
import { Platform, Text } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { NLSearchBar } from "@/src/components/NLSearchBar";
import { QueryProvider, useQuery } from "@/src/state/QueryProvider";

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
});

// Rendered probe — writes provider state into the DOM so waitFor() can poll
// the rendered tree directly instead of relying on a JS variable updated by
// a useEffect (which CI's React/jest-expo combo did not reliably surface).
function Probe(props: { initialMode?: "nl" | "filters" }) {
  const q = useQuery();
  const initialModeApplied = React.useRef(false);
  React.useEffect(() => {
    if (props.initialMode && !initialModeApplied.current) {
      initialModeApplied.current = true;
      if (q.mode !== props.initialMode) q.setMode(props.initialMode);
    }
  }, [props.initialMode, q]);
  return (
    <>
      <Text testID="probe-mode">{q.mode}</Text>
      <Text testID="probe-bedrooms-min">{q.query.bedrooms_min ?? ""}</Text>
      <Text testID="probe-neighborhoods">{q.query.neighborhoods.join(",")}</Text>
    </>
  );
}

function renderBar(initialMode?: "nl" | "filters") {
  return render(
    <QueryProvider>
      <Probe initialMode={initialMode} />
      <NLSearchBar apiBaseUrl="http://api.test" />
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
    const { getByLabelText, getByText, getByTestId } = renderBar();
    fireEvent.changeText(getByLabelText("Search input"), "2br Kits under 3000");
    fireEvent.press(getByText("Parse"));
    await waitFor(() =>
      expect(getByTestId("probe-bedrooms-min").props.children).toBe(2)
    );
    expect(getByTestId("probe-neighborhoods").props.children).toBe("Kitsilano");
  });

  it("falls back to filter mode on 5xx", async () => {
    mockTranslate({ detail: { error: "llm_transport_error" } }, false, 502);
    const { getByLabelText, getByText, getByTestId, findByText } = renderBar("nl");
    fireEvent.changeText(getByLabelText("Search input"), "anything");
    fireEvent.press(getByText("Parse"));
    await findByText(/LLM unavailable/i);
    await waitFor(() => expect(getByTestId("probe-mode").props.children).toBe("filters"));
  });

  it("falls back on network error", async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new TypeError("Network down"));
    const { getByLabelText, getByText, getByTestId, findByText } = renderBar("nl");
    fireEvent.changeText(getByLabelText("Search input"), "anything");
    fireEvent.press(getByText("Parse"));
    await findByText(/LLM unavailable/i);
    await waitFor(() => expect(getByTestId("probe-mode").props.children).toBe("filters"));
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
