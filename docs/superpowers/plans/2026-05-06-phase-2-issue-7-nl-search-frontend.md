# Phase 2 Issue #7 — Frontend NL Search Bar + Mode Toggle + Parsed Chips

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a natural-language input on top of the existing filter UI. The user can type EN or KO ("2br Kits under 3000" / "키츠 2베드 3000불 이하"), see the parsed query as editable chips, and run the search. Both modes share the same `NormalizedQuery` state so switching between them never loses filters.

**Architecture:** A new `NLSearchBar` component above the existing `FilterPanel`. A `ModeToggle` ("Natural language" ⇄ "Filters") in the filter pane sets a `mode` flag in `QueryProvider`. When `mode === "nl"`, the filter pane shows the NL bar plus `ParsedQueryChips` reflecting the current `NormalizedQuery`. When `mode === "filters"`, the existing `FilterPanel` shows. On `/translate-query` 5xx or network error, we surface a toast/banner and auto-switch to `mode: "filters"`. Tests cover the parsing flow, chip removal, mode switch state preservation, and the error-fallback path. A Playwright smoke walks the full EN flow.

**Tech Stack:** Same as Phase 1 frontend (Expo/React Native primitives, TypeScript strict, jest + RTL, Playwright). No new top-level dependencies.

**Issue:** [#7](https://github.com/jfive-ai/rentwise/issues/7). Branch: `feat/phase-2-llm-frontend`.

---

## File Structure

| Path | Purpose |
|---|---|
| `apps/web/src/api/types.ts` (modify) | Add `TranslateQueryRequest`, `TranslateQueryResult` |
| `apps/web/src/api/client.ts` (modify) | Add `translateQuery` to `SearchClient` (rename to `apiClient` if it makes more sense — but minimal-change first) |
| `apps/web/src/state/QueryProvider.tsx` (modify) | Add `mode: "nl" \| "filters"`, `setMode`, `nlText`, `setNlText`. Switching Filters→NL clears `nlText`; switching NL→Filters preserves the structured query. |
| `apps/web/src/components/NLSearchBar.tsx` (new) | Textarea + Parse button + spinner; calls `translateQuery`; on error → toast + `setMode("filters")` |
| `apps/web/src/components/ParsedQueryChips.tsx` (new) | Renders the current `NormalizedQuery` as removable chips |
| `apps/web/src/components/ModeToggle.tsx` (new) | Pill switcher |
| `apps/web/src/screens/SearchScreen.tsx` (modify) | Render `ModeToggle` + (NL bar + chips) OR `FilterPanel` based on `mode` |
| `apps/web/src/state/__tests__/QueryProvider.test.tsx` (modify) | Tests for `mode`, `nlText`, mode-switch semantics |
| `apps/web/src/components/__tests__/NLSearchBar.test.tsx` (new) | Submission flow + error/fallback path |
| `apps/web/src/components/__tests__/ParsedQueryChips.test.tsx` (new) | Chip rendering, removal, "+ Add filter" |
| `apps/web/src/components/__tests__/ModeToggle.test.tsx` (new) | Mode switch updates context |
| `apps/web/e2e/nl-search.smoke.spec.ts` (new) | Playwright: type EN → Parse → chips → Search → results |

---

## Task 1: API client + types for `/translate-query`

**Files:**
- Modify: `apps/web/src/api/types.ts`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/__tests__/client.test.ts` (existing file, extend)

- [ ] **Step 1: Add types**

In `apps/web/src/api/types.ts`, append:

```typescript
export interface TranslateQueryRequest {
  text: string;
}

export interface TranslateQueryResult {
  query: NormalizedQuery;
  unsupported_filters: string[];
  lang_detected: "en" | "ko";
  model_used: string;
}
```

- [ ] **Step 2: Extend the SearchClient interface and implementation**

In `apps/web/src/api/client.ts`, replace `interface SearchClient` and `searchClient` body:

```typescript
import type { SearchRequest, SearchResponse, TranslateQueryRequest, TranslateQueryResult } from "./types";

// ...existing ApiError stays unchanged...

export interface ApiClient {
  search(req: SearchRequest): Promise<SearchResponse>;
  translateQuery(req: TranslateQueryRequest): Promise<TranslateQueryResult>;
}

// Keep searchClient for backwards compatibility with existing imports, but
// now returns the broader ApiClient.
export function searchClient(baseUrl: string): ApiClient {
  const base = baseUrl.replace(/\/$/, "");

  async function call<T>(path: string, body: unknown): Promise<T> {
    let res: Response;
    try {
      res = await fetch(`${base}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (e) {
      throw new ApiError(0, e instanceof Error ? e.message : String(e));
    }
    if (!res.ok) {
      let payload: unknown;
      const cloned = res.clone();
      try {
        payload = await res.json();
      } catch {
        try { payload = await cloned.text(); } catch { /* unreadable */ }
      }
      throw new ApiError(res.status, `HTTP ${res.status}`, payload);
    }
    return (await res.json()) as T;
  }

  return {
    search(req) {
      return call<SearchResponse>("/search", req);
    },
    translateQuery(req) {
      return call<TranslateQueryResult>("/translate-query", req);
    },
  };
}

// Optional: also export apiClient as an alias to encourage the new name.
export const apiClient = searchClient;
```

(The renamed `call` helper deduplicates the fetch boilerplate; behavior identical.)

- [ ] **Step 3: Add tests for translateQuery**

In `apps/web/src/api/__tests__/client.test.ts`, append:

```typescript
describe("translateQuery", () => {
  it("POSTs to /translate-query and returns the parsed result", async () => {
    const fixture = {
      query: { neighborhoods: ["Kitsilano"], pets: "any", furnished: "any", free_text_keywords: [], bedrooms_min: 2, price_max: 3000 },
      unsupported_filters: [],
      lang_detected: "en",
      model_used: "openrouter/qwen/qwen-2.5-72b-instruct:free",
    };
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => fixture,
      clone: () => ({ text: async () => JSON.stringify(fixture) }),
    });
    (global as { fetch: unknown }).fetch = fetchMock;

    const client = searchClient("http://api.test/");
    const result = await client.translateQuery({ text: "2br Kits under 3000" });
    expect(result.lang_detected).toBe("en");
    expect(result.query.bedrooms_min).toBe(2);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/translate-query");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ text: "2br Kits under 3000" });
  });

  it("throws ApiError on 5xx", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({ detail: { error: "llm_transport_error", message: "down" } }),
      clone: () => ({ text: async () => '{"detail":{"error":"llm_transport_error"}}' }),
    });
    (global as { fetch: unknown }).fetch = fetchMock;

    await expect(searchClient("http://api.test").translateQuery({ text: "anything" }))
      .rejects.toMatchObject({ name: "ApiError", status: 502 });
  });
});
```

- [ ] **Step 4: Run + commit**

```bash
cd apps/web && npm test -- --testPathPattern=src/api/__tests__/client.test.ts
# expect prior client tests + 2 new = green

git add apps/web/src/api/types.ts apps/web/src/api/client.ts apps/web/src/api/__tests__/client.test.ts
git commit -m "feat(web): translateQuery on ApiClient (#7)"
```

---

## Task 2: Mode + NL text on `QueryProvider`

**Files:**
- Modify: `apps/web/src/state/QueryProvider.tsx`
- Modify: `apps/web/src/state/__tests__/QueryProvider.test.tsx`

The provider gains `mode: "nl" | "filters"` (default `"filters"`) and `nlText` (the raw NL input, persisted across re-parses). Switching from filters→NL clears `nlText`; switching nl→filters preserves the structured query but blanks `nlText`.

- [ ] **Step 1: Failing tests**

Append to `apps/web/src/state/__tests__/QueryProvider.test.tsx`:

```typescript
describe("mode + nlText", () => {
  it("defaults to filters mode and empty nlText", () => {
    const { result } = renderHook(() => useQuery(), { wrapper: QueryProvider });
    expect(result.current.mode).toBe("filters");
    expect(result.current.nlText).toBe("");
  });

  it("setMode updates mode", () => {
    const { result } = renderHook(() => useQuery(), { wrapper: QueryProvider });
    act(() => result.current.setMode("nl"));
    expect(result.current.mode).toBe("nl");
  });

  it("filters→nl clears nlText (no fake sentence)", () => {
    const { result } = renderHook(() => useQuery(), { wrapper: QueryProvider });
    act(() => result.current.setMode("nl"));
    act(() => result.current.setNlText("키츠 2베드"));
    act(() => result.current.setMode("filters"));
    act(() => result.current.setMode("nl"));
    // re-entered NL mode after filter mode → nlText cleared per spec
    expect(result.current.nlText).toBe("");
  });

  it("nl→filters preserves structured query", () => {
    const { result } = renderHook(() => useQuery(), { wrapper: QueryProvider });
    act(() => result.current.setMode("nl"));
    act(() => result.current.set({ bedrooms_min: 2, neighborhoods: ["Kitsilano"] }));
    act(() => result.current.setMode("filters"));
    expect(result.current.query.bedrooms_min).toBe(2);
    expect(result.current.query.neighborhoods).toEqual(["Kitsilano"]);
  });
});
```

(If `renderHook`/`act` aren't already imported in this file, add `import { act, renderHook } from "@testing-library/react-native";`.)

- [ ] **Step 2: Run; expect failure on `mode`/`setMode`/`nlText`/`setNlText`.**

- [ ] **Step 3: Implement**

In `apps/web/src/state/QueryProvider.tsx`, extend the context type and provider:

```typescript
type Mode = "nl" | "filters";

interface QueryContextValue {
  query: NormalizedQuery;
  set: (patch: Partial<NormalizedQuery>) => void;
  reset: () => void;
  toggleNeighborhood: (name: string) => void;
  toggleKeyword: (k: string) => void;
  // NL-specific:
  mode: Mode;
  setMode: (m: Mode) => void;
  nlText: string;
  setNlText: (s: string) => void;
}

// Inside QueryProvider:
const [mode, setModeRaw] = useState<Mode>("filters");
const [nlText, setNlText] = useState<string>("");

const setMode = useCallback((next: Mode) => {
  setModeRaw((prev) => {
    // Spec: every NL-mode entry starts with a clean text box (don't fake a
    // sentence from existing filters). The structured query is preserved.
    if (next === "nl") setNlText("");
    return next;
  });
}, []);

// in `value`:
const value = useMemo<QueryContextValue>(
  () => ({ query, set, reset, toggleNeighborhood, toggleKeyword, mode, setMode, nlText, setNlText }),
  [query, set, reset, toggleNeighborhood, toggleKeyword, mode, setMode, nlText]
);
```

- [ ] **Step 4: Run all QueryProvider tests; commit**

```bash
cd apps/web && npm test -- --testPathPattern=src/state/__tests__/QueryProvider
git add apps/web/src/state/QueryProvider.tsx apps/web/src/state/__tests__/QueryProvider.test.tsx
git commit -m "feat(web): mode + nlText state on QueryProvider (#7)"
```

---

## Task 3: ParsedQueryChips component

**Files:**
- Create: `apps/web/src/components/ParsedQueryChips.tsx`
- Create: `apps/web/src/components/__tests__/ParsedQueryChips.test.tsx`

Renders one chip per populated field of `NormalizedQuery`. Each chip has an ❌ that updates the query in the provider.

- [ ] **Step 1: Failing tests**

`apps/web/src/components/__tests__/ParsedQueryChips.test.tsx`:

```tsx
import React from "react";
import { fireEvent, render } from "@testing-library/react-native";
import { ParsedQueryChips } from "@/src/components/ParsedQueryChips";
import { QueryProvider, useQuery } from "@/src/state/QueryProvider";

function Probe(props: { onReady: (q: ReturnType<typeof useQuery>) => void }) {
  const q = useQuery();
  React.useEffect(() => props.onReady(q), [q]);
  return null;
}

function setUp(initial: Partial<{ bedrooms_min: number; price_max: number; neighborhoods: string[]; pets: "ok" | "no" }>) {
  let captured: ReturnType<typeof useQuery> | null = null;
  const utils = render(
    <QueryProvider>
      <Probe onReady={(q) => { captured = q; }} />
      <ParsedQueryChips />
    </QueryProvider>
  );
  // Seed
  if (initial) {
    captured!.set(initial as never);
    utils.rerender(
      <QueryProvider>
        <Probe onReady={(q) => { captured = q; }} />
        <ParsedQueryChips />
      </QueryProvider>
    );
  }
  return { ...utils, get captured() { return captured!; } };
}

describe("ParsedQueryChips", () => {
  it("renders one chip per populated field", () => {
    const { getByText } = render(
      <QueryProvider>
        <ParsedQueryChips />
      </QueryProvider>
    );
    // Empty query → empty state
    expect(getByText(/no filters parsed/i)).toBeTruthy();
  });

  it("chip removal clears that field", () => {
    let captured: ReturnType<typeof useQuery> | null = null;
    function Wrapper() {
      const q = useQuery();
      captured = q;
      return <ParsedQueryChips />;
    }
    const { getByLabelText, rerender } = render(
      <QueryProvider><Wrapper /></QueryProvider>
    );
    captured!.set({ bedrooms_min: 2 });
    rerender(<QueryProvider><Wrapper /></QueryProvider>);
    // Note: rerender re-mounts under our test setup; simpler approach:
    // skip full rerender and trust that the chip is rendered in a stable provider.
    // (See actual test implementation below — this is just a sketch.)
  });
});
```

The test above is intentionally rough. The implementer should adapt to the codebase's existing testing utility (look at how `FilterPanel.test.tsx` accesses provider state) and end up with three concrete tests:

- Renders empty-state copy when query has no populated fields.
- Renders the expected chips for a populated query (bedrooms, price, neighborhoods, pets, furnished, available_after, transit, school catchment, free-text keywords).
- Pressing a chip's ❌ button clears the corresponding field — assert via the test probe that `query.bedrooms_min` becomes `null`.

If existing tests in this repo use a render-and-then-`fireEvent` pattern with a `Probe` component to inspect provider state, follow that.

- [ ] **Step 2: Implement**

`apps/web/src/components/ParsedQueryChips.tsx`:

```tsx
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useQuery } from "@/src/state/QueryProvider";
import { useTheme } from "@/src/theme";

interface Chip {
  key: string;
  label: string;
  clear: () => void;
}

export function ParsedQueryChips() {
  const t = useTheme();
  const { query, set } = useQuery();

  const chips: Chip[] = [];
  if (query.bedrooms_min != null) {
    chips.push({
      key: "beds_min",
      label: `${query.bedrooms_min}+ beds`,
      clear: () => set({ bedrooms_min: null }),
    });
  }
  if (query.bedrooms_max != null) {
    chips.push({
      key: "beds_max",
      label: `≤${query.bedrooms_max} beds`,
      clear: () => set({ bedrooms_max: null }),
    });
  }
  if (query.price_min != null) {
    chips.push({
      key: "price_min",
      label: `≥$${query.price_min}`,
      clear: () => set({ price_min: null }),
    });
  }
  if (query.price_max != null) {
    chips.push({
      key: "price_max",
      label: `≤$${query.price_max}`,
      clear: () => set({ price_max: null }),
    });
  }
  for (const n of query.neighborhoods) {
    chips.push({
      key: `nbhd_${n}`,
      label: n,
      clear: () => set({ neighborhoods: query.neighborhoods.filter((x) => x !== n) }),
    });
  }
  if (query.school_catchment) {
    chips.push({
      key: "school",
      label: `${query.school_catchment} catchment`,
      clear: () => set({ school_catchment: null }),
    });
  }
  if (query.pets !== "any") {
    chips.push({
      key: "pets",
      label: query.pets === "required" ? "pets required" : query.pets === "no" ? "no pets" : "pets ok",
      clear: () => set({ pets: "any" }),
    });
  }
  if (query.furnished !== "any") {
    chips.push({
      key: "furn",
      label: query.furnished === "yes" ? "furnished" : "unfurnished",
      clear: () => set({ furnished: "any" }),
    });
  }
  if (query.available_after) {
    chips.push({
      key: "avail",
      label: `from ${query.available_after}`,
      clear: () => set({ available_after: null }),
    });
  }
  if (query.transit_max_walk_minutes != null) {
    chips.push({
      key: "walk",
      label: `≤${query.transit_max_walk_minutes} min walk`,
      clear: () => set({ transit_max_walk_minutes: null }),
    });
  }
  for (const kw of query.free_text_keywords) {
    chips.push({
      key: `kw_${kw}`,
      label: `"${kw}"`,
      clear: () => set({ free_text_keywords: query.free_text_keywords.filter((x) => x !== kw) }),
    });
  }

  if (chips.length === 0) {
    return (
      <View style={styles.emptyWrap}>
        <Text style={{ color: t.muted, fontSize: 13 }}>
          No filters parsed yet — type a search above and press Parse.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      {chips.map((c) => (
        <Pressable
          key={c.key}
          accessibilityRole="button"
          accessibilityLabel={`Remove ${c.label}`}
          onPress={c.clear}
          style={[styles.chip, { borderColor: t.border, backgroundColor: t.surface }]}
        >
          <Text style={{ color: t.text }}>
            {c.label} <Text style={{ color: t.muted }}>×</Text>
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  emptyWrap: { paddingVertical: 8 },
  chip: { paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderRadius: 999 },
});
```

- [ ] **Step 3: Finalize tests, run, commit**

Implementer should rewrite the rough test sketch above into 3 clean tests using the codebase's idiomatic `Probe` pattern (look at `apps/web/src/state/__tests__/QueryProvider.test.tsx` for examples). Goal:

1. Empty-state copy renders when query is empty.
2. Each populated field produces a chip (test seeds bedrooms_min=2 + neighborhoods=["Kitsilano"] + pets="ok" and asserts those three chips exist).
3. Pressing the ❌ for a chip clears that field on the query (assert via Probe).

```bash
cd apps/web && npm test -- --testPathPattern=ParsedQueryChips
git add apps/web/src/components/ParsedQueryChips.tsx apps/web/src/components/__tests__/ParsedQueryChips.test.tsx
git commit -m "feat(web): ParsedQueryChips with per-field removal (#7)"
```

---

## Task 4: NLSearchBar component

**Files:**
- Create: `apps/web/src/components/NLSearchBar.tsx`
- Create: `apps/web/src/components/__tests__/NLSearchBar.test.tsx`

Textarea bound to `query.nlText` from the provider. "Parse" button triggers `apiClient.translateQuery({ text })`. On success: writes the returned `query` back into the provider via `reset()` then a single `set(...)` (so chips reflect *only* the LLM's interpretation). On 5xx/network: shows an inline banner "LLM unavailable — switched to filter mode" and calls `setMode("filters")`.

- [ ] **Step 1: Failing tests**

`apps/web/src/components/__tests__/NLSearchBar.test.tsx`:

```tsx
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

function Probe(props: { onReady: (q: ReturnType<typeof useQuery>) => void }) {
  const q = useQuery();
  React.useEffect(() => props.onReady(q), [q]);
  return null;
}

function renderBar(probe?: (q: ReturnType<typeof useQuery>) => void) {
  return render(
    <QueryProvider>
      {probe ? <Probe onReady={probe} /> : null}
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
      query: { neighborhoods: ["Kitsilano"], pets: "any", furnished: "any", free_text_keywords: [], bedrooms_min: 2, price_max: 3000 },
      unsupported_filters: [],
      lang_detected: "en",
      model_used: "m",
    });
    const { getByLabelText, getByText } = renderBar((q) => { captured = q; });
    fireEvent.changeText(getByLabelText("Search input"), "2br Kits under 3000");
    fireEvent.press(getByText("Parse"));
    await waitFor(() => expect(captured!.query.bedrooms_min).toBe(2));
    expect(captured!.query.neighborhoods).toEqual(["Kitsilano"]);
  });

  it("falls back to filter mode on 5xx", async () => {
    let captured: ReturnType<typeof useQuery> | null = null;
    mockTranslate({ detail: { error: "llm_transport_error" } }, false, 502);
    const { getByLabelText, getByText, findByText } = renderBar((q) => {
      captured = q;
      // Start in NL mode so the fallback can flip back.
      if (q.mode !== "nl") q.setMode("nl");
    });
    fireEvent.changeText(getByLabelText("Search input"), "anything");
    fireEvent.press(getByText("Parse"));
    await findByText(/LLM unavailable/i);
    await waitFor(() => expect(captured!.mode).toBe("filters"));
  });

  it("falls back on network error", async () => {
    let captured: ReturnType<typeof useQuery> | null = null;
    jest.spyOn(global, "fetch").mockRejectedValue(new TypeError("Network down"));
    const { getByLabelText, getByText, findByText } = renderBar((q) => {
      captured = q;
      if (q.mode !== "nl") q.setMode("nl");
    });
    fireEvent.changeText(getByLabelText("Search input"), "anything");
    fireEvent.press(getByText("Parse"));
    await findByText(/LLM unavailable/i);
    await waitFor(() => expect(captured!.mode).toBe("filters"));
  });

  it("disables Parse while a request is in flight", async () => {
    let resolveFetch: ((v: unknown) => void) | undefined;
    const pending = new Promise((r) => { resolveFetch = r; });
    jest.spyOn(global, "fetch").mockImplementation(() => pending as never);
    const { getByLabelText, getByText } = renderBar();
    fireEvent.changeText(getByLabelText("Search input"), "1br anywhere");
    fireEvent.press(getByText("Parse"));
    expect(getByText(/Parsing/i)).toBeTruthy();
    resolveFetch!({
      ok: true, status: 200,
      json: async () => ({ query: { neighborhoods: [], pets: "any", furnished: "any", free_text_keywords: [], bedrooms_min: 1 }, unsupported_filters: [], lang_detected: "en", model_used: "m" }),
      clone: () => ({ text: async () => "{}" }),
    });
    await waitFor(() => expect(getByText("Parse")).toBeTruthy());
  });
});
```

- [ ] **Step 2: Implement**

`apps/web/src/components/NLSearchBar.tsx`:

```tsx
import React, { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { searchClient } from "@/src/api/client";
import { useQuery } from "@/src/state/QueryProvider";
import { useTheme } from "@/src/theme";
import { emptyQuery } from "@/src/api/types";

interface Props {
  apiBaseUrl: string;
}

export function NLSearchBar({ apiBaseUrl }: Props) {
  const t = useTheme();
  const { nlText, setNlText, set, reset, setMode } = useQuery();
  const client = useMemo(() => searchClient(apiBaseUrl), [apiBaseUrl]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onParse = useCallback(async () => {
    const text = nlText.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      const result = await client.translateQuery({ text });
      // Replace structured query with LLM's interpretation, preserving nothing
      // from the previous filters (this is what the user asked for via NL).
      reset();
      set(result.query);
    } catch {
      setError("LLM unavailable — switched to filter mode. Try again or use the filter UI.");
      setMode("filters");
    } finally {
      setBusy(false);
    }
  }, [client, nlText, reset, set, setMode]);

  return (
    <View style={[styles.wrap, { borderColor: t.border, backgroundColor: t.surface }]}>
      <TextInput
        accessibilityLabel="Search input"
        placeholder="Try: 2 bedroom in Kitsilano under 3000 pet ok"
        placeholderTextColor={t.muted}
        value={nlText}
        onChangeText={setNlText}
        editable={!busy}
        multiline
        style={[styles.input, { color: t.text, borderColor: t.border }]}
      />
      <View style={styles.row}>
        <Pressable
          accessibilityRole="button"
          onPress={onParse}
          disabled={busy || nlText.trim().length === 0}
          style={[styles.parseBtn, { backgroundColor: busy ? t.muted : t.accent }]}
        >
          {busy ? (
            <View style={styles.btnInner}>
              <ActivityIndicator size="small" color="#fff" />
              <Text style={styles.parseBtnText}>Parsing…</Text>
            </View>
          ) : (
            <Text style={styles.parseBtnText}>Parse</Text>
          )}
        </Pressable>
      </View>
      {error ? <Text style={[styles.error, { color: t.danger ?? "#c00" }]}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 12, borderWidth: 1, borderRadius: 8, gap: 8 },
  input: { minHeight: 56, padding: 8, borderWidth: 1, borderRadius: 6, textAlignVertical: "top" },
  row: { flexDirection: "row", justifyContent: "flex-end" },
  btnInner: { flexDirection: "row", alignItems: "center", gap: 6 },
  parseBtn: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 6 },
  parseBtnText: { color: "#fff", fontWeight: "600" },
  error: { marginTop: 4, fontSize: 13 },
});
```

(If `Theme` doesn't have a `danger` key today, the `?? "#c00"` fallback keeps things safe; you can leave that.)

- [ ] **Step 3: Run + commit**

```bash
cd apps/web && npm test -- --testPathPattern=NLSearchBar
git add apps/web/src/components/NLSearchBar.tsx apps/web/src/components/__tests__/NLSearchBar.test.tsx
git commit -m "feat(web): NLSearchBar with parse + graceful fallback (#7)"
```

---

## Task 5: ModeToggle + integrate into SearchScreen

**Files:**
- Create: `apps/web/src/components/ModeToggle.tsx`
- Create: `apps/web/src/components/__tests__/ModeToggle.test.tsx`
- Modify: `apps/web/src/screens/SearchScreen.tsx`
- Modify: `apps/web/src/screens/__tests__/SearchScreen.test.tsx`

The toggle is a two-button pill. When `mode === "nl"`, the filter pane shows `NLSearchBar` + `ParsedQueryChips`; when `"filters"`, the existing `FilterPanel`.

- [ ] **Step 1: ModeToggle**

`apps/web/src/components/ModeToggle.tsx`:

```tsx
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useQuery } from "@/src/state/QueryProvider";
import { useTheme } from "@/src/theme";

export function ModeToggle() {
  const t = useTheme();
  const { mode, setMode } = useQuery();
  return (
    <View style={[styles.wrap, { borderColor: t.border }]}>
      <Pill label="Natural language" active={mode === "nl"} onPress={() => setMode("nl")} />
      <Pill label="Filters" active={mode === "filters"} onPress={() => setMode("filters")} />
    </View>
  );
}

function Pill({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      accessibilityLabel={label}
      onPress={onPress}
      style={[
        styles.pill,
        {
          backgroundColor: active ? t.accent : "transparent",
        },
      ]}
    >
      <Text style={{ color: active ? "#fff" : t.text, fontSize: 13, fontWeight: "600" }}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: "row", borderWidth: 1, borderRadius: 999, padding: 2, alignSelf: "flex-start" },
  pill: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 999 },
});
```

Tests: `apps/web/src/components/__tests__/ModeToggle.test.tsx` — 2 short tests:
1. "Natural language" press → `mode === "nl"`.
2. "Filters" press → `mode === "filters"`.

- [ ] **Step 2: Wire into SearchScreen**

In `apps/web/src/screens/SearchScreen.tsx`, near the top of the filter pane render, replace:

```tsx
<View style={[styles.filters, { borderColor: t.border, backgroundColor: t.surface }]}>
  <FilterPanel onSearch={onSearch} />
</View>
```

with:

```tsx
<View style={[styles.filters, { borderColor: t.border, backgroundColor: t.surface }]}>
  <View style={styles.modeRow}>
    <ModeToggle />
  </View>
  {mode === "nl" ? (
    <View style={styles.nlPane}>
      <NLSearchBar apiBaseUrl={apiBaseUrl} />
      <ParsedQueryChips />
      <Pressable
        accessibilityRole="button"
        onPress={onSearch}
        style={[styles.searchBtn, { backgroundColor: t.accent }]}
      >
        <Text style={{ color: "#fff", fontWeight: "600" }}>Search</Text>
      </Pressable>
    </View>
  ) : (
    <FilterPanel onSearch={onSearch} />
  )}
</View>
```

Add `const { query, mode } = useQuery();` (replace existing destructuring), import the three new components and add the matching styles:

```tsx
modeRow: { padding: 12, borderBottomWidth: 1, borderColor: "transparent" },
nlPane: { padding: 12, gap: 12 },
searchBtn: { alignSelf: "flex-end", paddingHorizontal: 18, paddingVertical: 10, borderRadius: 8 },
```

- [ ] **Step 3: Update SearchScreen tests**

Existing `SearchScreen.test.tsx` tests start in default (filter) mode and press the rendered "Search" button. They keep working because `FilterPanel.tsx` already renders a "Search" button. To prove the new wiring, add ONE new test:

```tsx
it("NL mode → typing + Parse → chips appear → Search uses parsed query", async () => {
  // Initial mock: /translate-query
  (global.fetch as jest.Mock).mockResolvedValueOnce({
    ok: true, status: 200,
    json: async () => ({
      query: { neighborhoods: ["Kitsilano"], pets: "any", furnished: "any", free_text_keywords: [], bedrooms_min: 2 },
      unsupported_filters: [], lang_detected: "en", model_used: "m",
    }),
    clone: () => ({ text: async () => "{}" }),
  });
  // /search default mock comes from beforeEach.
  const { getByText, getByLabelText, findByText } = renderScreen();
  fireEvent.press(getByLabelText("Natural language"));
  fireEvent.changeText(getByLabelText("Search input"), "2br Kits");
  fireEvent.press(getByText("Parse"));
  await findByText("Kitsilano"); // chip appeared
  fireEvent.press(getByText("Search"));
  await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
  // The Search call must include neighborhoods: ["Kitsilano"]
  const lastSearch = (global.fetch as jest.Mock).mock.calls.find(
    (c) => (c[0] as string).endsWith("/search")
  );
  expect(JSON.parse(lastSearch![1].body).query.neighborhoods).toEqual(["Kitsilano"]);
});
```

- [ ] **Step 4: Run all web tests**

```bash
cd apps/web && npm test
# expect prior 54 + new tests, all green
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/ModeToggle.tsx apps/web/src/components/__tests__/ModeToggle.test.tsx apps/web/src/screens/SearchScreen.tsx apps/web/src/screens/__tests__/SearchScreen.test.tsx
git commit -m "feat(web): mode toggle + NL pane in SearchScreen (#7)"
```

---

## Task 6: Playwright smoke E2E

**Files:**
- Create: `apps/web/e2e/nl-search.smoke.spec.ts`

- [ ] **Step 1: Write the smoke test**

```typescript
import { test, expect } from "@playwright/test";

const SEARCH_FIXTURE = require("../__fixtures__/search_response.json");

test("NL flow: type → parse → chips → search", async ({ page }) => {
  await page.route("**/translate-query", async (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
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
        model_used: "openrouter/qwen/qwen-2.5-72b-instruct:free",
      }),
    });
  });
  await page.route("**/search", async (route) => {
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(SEARCH_FIXTURE) });
  });

  await page.goto("http://localhost:8081");

  // Switch to NL mode
  await page.getByRole("button", { name: "Natural language" }).click();
  await page.getByLabel("Search input").fill("2 bedroom in Kitsilano under 3000");
  await page.getByRole("button", { name: "Parse" }).click();

  // Chip appears
  await expect(page.getByText("Kitsilano")).toBeVisible();
  await expect(page.getByText("≤$3000")).toBeVisible();
  await expect(page.getByText("2+ beds")).toBeVisible();

  // Search
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText("5 listings")).toBeVisible();
});
```

- [ ] **Step 2: Run the smoke test**

```bash
cd apps/web && npm run e2e -- nl-search.smoke.spec.ts
# expect 1 PASS
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/e2e/nl-search.smoke.spec.ts
git commit -m "test(web): Playwright smoke for NL search flow (#7)"
```

---

## Task 7: Final lint + push + PR

- [ ] **Step 1: Lint + typecheck**

```bash
cd apps/web && npm run lint && npm run typecheck
```

- [ ] **Step 2: Push + PR**

```bash
git push -u origin feat/phase-2-llm-frontend

gh pr create --title "feat(web): NL search bar + mode toggle + parsed-query chips (#7)" --body "$(cat <<'EOF'
Closes #7.

## Summary
- `apiClient.translateQuery` calls the new `/translate-query` endpoint.
- `QueryProvider` gains `mode` and `nlText` state; switching modes preserves the structured query (filters→nl) and clears the text box on every NL re-entry per spec.
- `NLSearchBar` posts to `/translate-query`, replaces the structured query with the LLM's interpretation, and falls back to filter mode on any LLM error.
- `ParsedQueryChips` renders one chip per populated `NormalizedQuery` field with per-field removal.
- `ModeToggle` flips the filter pane between NL and Filters.
- `SearchScreen` renders `<ModeToggle/>` above the filter pane and switches its body based on `mode`.

## Test plan
- [x] jest+RTL: ApiClient.translateQuery, QueryProvider mode/nlText, NLSearchBar (success + 5xx + network), ParsedQueryChips (empty + populated + removal), ModeToggle, SearchScreen end-to-end NL flow
- [x] Playwright smoke: type EN → Parse → chips → Search → results
- [x] tsc + eslint clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Commit the plan file**

```bash
git add docs/superpowers/plans/2026-05-06-phase-2-issue-7-nl-search-frontend.md
git commit -m "docs: add Phase 2 Issue #7 implementation plan"
git push
```

---

## Done checklist (Issue #7)

- [ ] Tasks 1–6 complete with green tests
- [ ] Branch `feat/phase-2-llm-frontend` pushed
- [ ] PR opened, links to #7
- [ ] CI green
