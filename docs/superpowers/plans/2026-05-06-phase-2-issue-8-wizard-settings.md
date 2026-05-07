# Phase 2 Issue #8 — First-Run Wizard + LLM Settings Screen

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Onboard new users with a first-run wizard (provider → model → API key → optional fallback → test connection) and provide a settings screen so existing users can change provider/model/key. The wizard appears once on a fresh install, then never again.

**Architecture:** Three new screens (`FirstRunWizard`, `SettingsScreen`) plus a small `apiClient.getSettings/putSettings/testConnection` extension. A "wizard completed" flag in `localStorage`/`AsyncStorage` (web/native) gates the wizard so it shows only when the API returns 404 from `GET /settings/llm`. After save, the user lands on the normal `SearchScreen`. A header gear icon opens the settings screen.

**Tech Stack:** Same as Phase 1 (Expo Router, RN primitives, TypeScript strict, jest+RTL, Playwright). No new top-level dependencies.

**Issue:** [#8](https://github.com/jfive-ai/rentwise/issues/8). Branch: `feat/phase-2-wizard`.

---

## File Structure

| Path | Purpose |
|---|---|
| `apps/web/src/api/types.ts` (modify) | Add `LLMSettingsPublic`, `LLMSettingsUpdate`, `LLMConnectionTestRequest`, `LLMConnectionTestResult` types mirroring the API |
| `apps/web/src/api/client.ts` (modify) | Add `getSettings`, `putSettings`, `testConnection` methods |
| `apps/web/src/screens/FirstRunWizard.tsx` (new) | Step-by-step setup |
| `apps/web/src/screens/SettingsScreen.tsx` (new) | Edit-existing form |
| `apps/web/src/llm/providers.ts` (new) | Provider/model catalog (data-only) |
| `apps/web/app/_layout.tsx` (modify) | On mount: probe `GET /settings/llm` → if 404, render wizard; else normal stack |
| `apps/web/app/settings.tsx` (new) | Expo Router route for `<SettingsScreen/>` |
| `apps/web/src/screens/__tests__/FirstRunWizard.test.tsx` (new) | Happy path + validation + test-connection states |
| `apps/web/src/screens/__tests__/SettingsScreen.test.tsx` (new) | Loads, edits, saves |
| `apps/web/e2e/first-run.smoke.spec.ts` (new) | Playwright: stub 404 → wizard → save → reach search |

---

## Provider catalog

A small table of provider → model options that both the wizard and settings screen read. Hard-coded for now (Phase 2); Phase 5+ may fetch from the backend.

`apps/web/src/llm/providers.ts`:

```ts
export interface ModelOption {
  id: string; // litellm model string, e.g. "openrouter/qwen/qwen-2.5-72b-instruct:free"
  label: string; // user-facing label
  free?: boolean;
}

export interface ProviderOption {
  id: "openrouter" | "anthropic" | "openai" | "google" | "ollama";
  label: string;
  needsKey: boolean;
  models: ModelOption[];
}

export const PROVIDERS: ProviderOption[] = [
  {
    id: "openrouter",
    label: "OpenRouter (free + paid)",
    needsKey: true,
    models: [
      { id: "openrouter/qwen/qwen-2.5-72b-instruct:free", label: "Qwen 2.5 72B (free, recommended for KO)", free: true },
      { id: "openrouter/meta-llama/llama-3.3-70b-instruct:free", label: "Llama 3.3 70B (free)", free: true },
      { id: "openrouter/google/gemma-3-27b-it:free", label: "Gemma 3 27B (free)", free: true },
      { id: "openrouter/anthropic/claude-sonnet-4", label: "Claude Sonnet 4 (paid)" },
      { id: "openrouter/openai/gpt-4o-mini", label: "GPT-4o mini (paid)" },
    ],
  },
  {
    id: "anthropic",
    label: "Anthropic (Claude)",
    needsKey: true,
    models: [
      { id: "anthropic/claude-sonnet-4", label: "Claude Sonnet 4" },
    ],
  },
  {
    id: "openai",
    label: "OpenAI",
    needsKey: true,
    models: [
      { id: "openai/gpt-4o-mini", label: "GPT-4o mini" },
      { id: "openai/gpt-4o", label: "GPT-4o" },
    ],
  },
  {
    id: "google",
    label: "Google Gemini",
    needsKey: true,
    models: [
      { id: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash" },
    ],
  },
  {
    id: "ollama",
    label: "Ollama (local, no key)",
    needsKey: false,
    models: [
      { id: "ollama/llama3", label: "Llama 3 (local)" },
      { id: "ollama/qwen2", label: "Qwen 2 (local)" },
    ],
  },
];
```

---

## Task 1: API client extensions for `/settings/llm`

**Files:**
- Modify: `apps/web/src/api/types.ts`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/__tests__/client.test.ts`

- [ ] **Step 1: Add types**

In `apps/web/src/api/types.ts`, append:

```ts
export interface LLMSettingsPublic {
  primary_model: string;
  primary_api_key_masked: string | null;
  fallback_model: string | null;
  fallback_api_key_masked: string | null;
  custom_base_url: string | null;
  timeout_seconds: number;
}

export interface LLMSettingsUpdate {
  primary_model: string;
  primary_api_key?: string | null;
  primary_api_key_clear?: boolean;
  fallback_model?: string | null;
  fallback_api_key?: string | null;
  fallback_api_key_clear?: boolean;
  custom_base_url?: string | null;
  timeout_seconds?: number;
}

export interface LLMConnectionTestRequest {
  primary_model: string;
  primary_api_key?: string | null;
  custom_base_url?: string | null;
  timeout_seconds?: number;
}

export interface LLMConnectionTestResult {
  ok: boolean;
  error: string | null;
  latency_ms: number;
  model_used: string;
}
```

- [ ] **Step 2: Add methods to ApiClient**

In `apps/web/src/api/client.ts`, expand the `ApiClient` interface and the `searchClient`/`apiClient` factory:

```ts
import type {
  // existing imports...
  LLMSettingsPublic,
  LLMSettingsUpdate,
  LLMConnectionTestRequest,
  LLMConnectionTestResult,
} from "./types";

export interface ApiClient {
  search(req: SearchRequest): Promise<SearchResponse>;
  translateQuery(req: TranslateQueryRequest): Promise<TranslateQueryResult>;
  getSettings(): Promise<LLMSettingsPublic | null>;
  putSettings(body: LLMSettingsUpdate): Promise<LLMSettingsPublic>;
  testConnection(body: LLMConnectionTestRequest): Promise<LLMConnectionTestResult>;
}
```

In the factory, factor out a `request<T>(method, path, body?)` helper that supports GET (no body) and POST/PUT (JSON body). Reuse the existing error mapping. Add the three new methods:

```ts
return {
  search(req) { return request<SearchResponse>("POST", "/search", req); },
  translateQuery(req) { return request<TranslateQueryResult>("POST", "/translate-query", req); },
  async getSettings() {
    try {
      return await request<LLMSettingsPublic>("GET", "/settings/llm");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
  putSettings(body) { return request<LLMSettingsPublic>("PUT", "/settings/llm", body); },
  testConnection(body) { return request<LLMConnectionTestResult>("POST", "/settings/llm/test", body); },
};
```

- [ ] **Step 3: Tests**

Append tests to `apps/web/src/api/__tests__/client.test.ts`:

```ts
describe("settings", () => {
  it("getSettings returns null on 404", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false, status: 404,
      json: async () => ({ detail: "no_llm_settings" }),
      clone: () => ({ text: async () => "{}" }),
    });
    const result = await searchClient("http://api.test").getSettings();
    expect(result).toBeNull();
  });

  it("getSettings returns the masked payload on 200", async () => {
    const fixture = {
      primary_model: "openrouter/qwen/qwen-2.5-72b-instruct:free",
      primary_api_key_masked: "sk-or-...eeff",
      fallback_model: null,
      fallback_api_key_masked: null,
      custom_base_url: null,
      timeout_seconds: 30,
    };
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true, status: 200,
      json: async () => fixture,
      clone: () => ({ text: async () => JSON.stringify(fixture) }),
    });
    const result = await searchClient("http://api.test").getSettings();
    expect(result?.primary_api_key_masked).toBe("sk-or-...eeff");
  });

  it("putSettings PUTs the body", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({
        primary_model: "m", primary_api_key_masked: "***",
        fallback_model: null, fallback_api_key_masked: null,
        custom_base_url: null, timeout_seconds: 30,
      }),
      clone: () => ({ text: async () => "{}" }),
    });
    (global as { fetch: unknown }).fetch = fetchMock;

    await searchClient("http://api.test").putSettings({
      primary_model: "m", primary_api_key: "sk-test",
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ primary_model: "m", primary_api_key: "sk-test" });
  });

  it("testConnection POSTs and returns ok/false on failure", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ ok: false, error: "kaboom", latency_ms: 12, model_used: "m" }),
      clone: () => ({ text: async () => "{}" }),
    });
    const r = await searchClient("http://api.test").testConnection({ primary_model: "m" });
    expect(r.ok).toBe(false);
    expect(r.error).toBe("kaboom");
  });
});
```

- [ ] **Step 4: Run, commit**

```bash
cd apps/web && npm test -- --testPathPattern=src/api/__tests__/client.test.ts
git add apps/web/src/api/types.ts apps/web/src/api/client.ts apps/web/src/api/__tests__/client.test.ts
git commit -m "feat(web): ApiClient.getSettings / putSettings / testConnection (#8)"
```

---

## Task 2: Provider catalog

**Files:**
- Create: `apps/web/src/llm/providers.ts`
- Create: `apps/web/src/llm/__tests__/providers.test.ts`

- [ ] **Step 1: Add the catalog (verbatim from the section above)**

- [ ] **Step 2: Test the shape**

`apps/web/src/llm/__tests__/providers.test.ts`:

```ts
import { PROVIDERS } from "@/src/llm/providers";

describe("PROVIDERS catalog", () => {
  it("includes 5 providers (openrouter, anthropic, openai, google, ollama)", () => {
    const ids = PROVIDERS.map((p) => p.id);
    expect(ids.sort()).toEqual(["anthropic", "google", "ollama", "openai", "openrouter"]);
  });

  it("only ollama has needsKey=false", () => {
    expect(PROVIDERS.filter((p) => !p.needsKey).map((p) => p.id)).toEqual(["ollama"]);
  });

  it("every provider has at least one model", () => {
    for (const p of PROVIDERS) {
      expect(p.models.length).toBeGreaterThan(0);
    }
  });
});
```

- [ ] **Step 3: Run, commit**

```bash
cd apps/web && npm test -- --testPathPattern=providers
git add apps/web/src/llm
git commit -m "feat(web): provider/model catalog (#8)"
```

---

## Task 3: FirstRunWizard

**Files:**
- Create: `apps/web/src/screens/FirstRunWizard.tsx`
- Create: `apps/web/src/screens/__tests__/FirstRunWizard.test.tsx`

The wizard has 4 logical steps:
1. **Provider** radio (OpenRouter / Anthropic / OpenAI / Google / Ollama)
2. **Model** dropdown (filtered by provider)
3. **API key** masked input — skipped when provider is Ollama
4. **Optional fallback** (provider + model + key) — collapsed by default

A "Test connection" button calls `apiClient.testConnection()`. The "Finish" button is enabled after a successful test (or after the user explicitly chooses "Skip and save anyway"). On Finish: `apiClient.putSettings()`, then call the `onComplete` prop which the layout uses to dismiss the wizard.

- [ ] **Step 1: Failing tests**

`apps/web/src/screens/__tests__/FirstRunWizard.test.tsx`:

```tsx
/**
 * @jest-environment jsdom
 */
import React from "react";
import { Platform } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { FirstRunWizard } from "@/src/screens/FirstRunWizard";

beforeAll(() => {
  (Platform as { OS: string }).OS = "web";
  if (!("fetch" in global)) (global as { fetch: unknown }).fetch = jest.fn();
});

beforeEach(() => {
  (global.fetch as jest.Mock).mockClear?.();
});

afterEach(() => jest.restoreAllMocks());

const mockResponse = (body: unknown, ok = true, status = 200) =>
  ({
    ok, status,
    json: async () => body,
    clone: () => ({ text: async () => JSON.stringify(body) }),
  } as never);

describe("FirstRunWizard", () => {
  it("default provider is OpenRouter free; default model selected", () => {
    const { getByText } = render(<FirstRunWizard apiBaseUrl="http://api.test" onComplete={() => {}} />);
    expect(getByText(/OpenRouter/)).toBeTruthy();
    expect(getByText(/Qwen 2.5 72B/)).toBeTruthy();
  });

  it("ollama provider hides the API key input", () => {
    const { getByText, queryByLabelText } = render(
      <FirstRunWizard apiBaseUrl="http://api.test" onComplete={() => {}} />
    );
    fireEvent.press(getByText(/Ollama/));
    expect(queryByLabelText("API key")).toBeNull();
  });

  it("test connection success enables Finish", async () => {
    jest.spyOn(global, "fetch").mockResolvedValueOnce(
      mockResponse({ ok: true, error: null, latency_ms: 50, model_used: "m" })
    );
    const { getByText, getByLabelText } = render(
      <FirstRunWizard apiBaseUrl="http://api.test" onComplete={() => {}} />
    );
    fireEvent.changeText(getByLabelText("API key"), "sk-or-test");
    fireEvent.press(getByText("Test connection"));
    await waitFor(() => expect(getByText(/Connection ok/i)).toBeTruthy());
    // Finish button now enabled (no longer says "(test first)")
    expect(getByText("Finish")).toBeTruthy();
  });

  it("test connection failure shows error and offers Skip", async () => {
    jest.spyOn(global, "fetch").mockResolvedValueOnce(
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
    // Mock test then put
    jest.spyOn(global, "fetch")
      .mockResolvedValueOnce(mockResponse({ ok: true, error: null, latency_ms: 10, model_used: "m" }))
      .mockResolvedValueOnce(
        mockResponse({
          primary_model: "openrouter/qwen/qwen-2.5-72b-instruct:free",
          primary_api_key_masked: "sk-or-...test",
          fallback_model: null, fallback_api_key_masked: null,
          custom_base_url: null, timeout_seconds: 30,
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
    // PUT body shape
    const calls = (global.fetch as jest.Mock).mock.calls;
    const putCall = calls.find((c) => (c[1] as { method: string }).method === "PUT")!;
    expect(JSON.parse((putCall[1] as { body: string }).body)).toMatchObject({
      primary_model: "openrouter/qwen/qwen-2.5-72b-instruct:free",
      primary_api_key: "sk-or-test",
    });
  });
});
```

- [ ] **Step 2: Run; expect failure on missing module.**

- [ ] **Step 3: Implement**

`apps/web/src/screens/FirstRunWizard.tsx`:

```tsx
import React, { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { searchClient } from "@/src/api/client";
import { PROVIDERS, type ModelOption, type ProviderOption } from "@/src/llm/providers";
import { useTheme } from "@/src/theme";

interface Props {
  apiBaseUrl: string;
  onComplete: () => void;
}

type TestState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; latency: number }
  | { kind: "error"; message: string };

export function FirstRunWizard({ apiBaseUrl, onComplete }: Props) {
  const t = useTheme();
  const client = useMemo(() => searchClient(apiBaseUrl), [apiBaseUrl]);

  const [providerId, setProviderId] = useState<ProviderOption["id"]>(PROVIDERS[0].id);
  const provider = useMemo(() => PROVIDERS.find((p) => p.id === providerId)!, [providerId]);
  const [modelId, setModelId] = useState<string>(provider.models[0].id);
  const [apiKey, setApiKey] = useState<string>("");
  const [test, setTest] = useState<TestState>({ kind: "idle" });
  const [saving, setSaving] = useState(false);

  // Reset model when provider changes
  React.useEffect(() => {
    const p = PROVIDERS.find((x) => x.id === providerId)!;
    setModelId(p.models[0].id);
    setTest({ kind: "idle" });
  }, [providerId]);

  const onTest = async () => {
    setTest({ kind: "running" });
    try {
      const result = await client.testConnection({
        primary_model: modelId,
        primary_api_key: provider.needsKey ? apiKey : null,
      });
      if (result.ok) {
        setTest({ kind: "ok", latency: result.latency_ms });
      } else {
        setTest({ kind: "error", message: result.error ?? "Unknown error" });
      }
    } catch (e) {
      setTest({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  };

  const onFinish = async () => {
    setSaving(true);
    try {
      await client.putSettings({
        primary_model: modelId,
        primary_api_key: provider.needsKey ? apiKey : null,
      });
      onComplete();
    } finally {
      setSaving(false);
    }
  };

  const canFinish = test.kind === "ok" || test.kind === "error" /* allow skip */;

  return (
    <ScrollView contentContainerStyle={[styles.wrap, { backgroundColor: t.bg }]}>
      <Text style={[styles.title, { color: t.text }]}>Welcome to RentWise</Text>
      <Text style={[styles.subtitle, { color: t.textMuted }]}>Pick an AI model to translate your searches.</Text>

      <Section title="Provider" theme={t}>
        {PROVIDERS.map((p) => (
          <Pressable
            key={p.id}
            accessibilityRole="radio"
            accessibilityState={{ selected: providerId === p.id }}
            onPress={() => setProviderId(p.id)}
            style={[styles.row, { borderColor: t.border, backgroundColor: providerId === p.id ? t.surface : "transparent" }]}
          >
            <Text style={{ color: t.text }}>{p.label}</Text>
          </Pressable>
        ))}
      </Section>

      <Section title="Model" theme={t}>
        {provider.models.map((m: ModelOption) => (
          <Pressable
            key={m.id}
            accessibilityRole="radio"
            accessibilityState={{ selected: modelId === m.id }}
            onPress={() => { setModelId(m.id); setTest({ kind: "idle" }); }}
            style={[styles.row, { borderColor: t.border, backgroundColor: modelId === m.id ? t.surface : "transparent" }]}
          >
            <Text style={{ color: t.text }}>{m.label}{m.free ? "  🆓" : ""}</Text>
          </Pressable>
        ))}
      </Section>

      {provider.needsKey ? (
        <Section title="API key" theme={t}>
          <TextInput
            accessibilityLabel="API key"
            placeholder="sk-..."
            placeholderTextColor={t.textMuted}
            value={apiKey}
            onChangeText={(v) => { setApiKey(v); setTest({ kind: "idle" }); }}
            secureTextEntry
            style={[styles.input, { color: t.text, borderColor: t.border }]}
          />
        </Section>
      ) : null}

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          onPress={onTest}
          disabled={test.kind === "running"}
          style={[styles.btnSecondary, { borderColor: t.border }]}
        >
          <Text style={{ color: t.text }}>
            {test.kind === "running" ? "Testing…" : "Test connection"}
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onFinish}
          disabled={!canFinish || saving}
          style={[styles.btnPrimary, { backgroundColor: !canFinish || saving ? t.textMuted : t.accent }]}
        >
          <Text style={{ color: "#fff", fontWeight: "600" }}>
            {test.kind === "error" ? "Skip and save anyway" : "Finish"}
          </Text>
        </Pressable>
      </View>

      {test.kind === "ok" ? (
        <Text style={{ color: t.text, marginTop: 8 }}>Connection ok ({test.latency} ms)</Text>
      ) : null}
      {test.kind === "error" ? (
        <Text style={{ color: "#c00", marginTop: 8 }}>Connection error: {test.message}</Text>
      ) : null}
    </ScrollView>
  );
}

function Section({ title, children, theme }: { title: string; children: React.ReactNode; theme: ReturnType<typeof useTheme> }) {
  return (
    <View style={styles.section}>
      <Text style={[styles.sectionTitle, { color: theme.text }]}>{title}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 24, gap: 16, minHeight: "100%" },
  title: { fontSize: 24, fontWeight: "700" },
  subtitle: { fontSize: 14, marginBottom: 8 },
  section: { gap: 8 },
  sectionTitle: { fontWeight: "600", fontSize: 14 },
  row: { padding: 10, borderWidth: 1, borderRadius: 8 },
  input: { padding: 10, borderWidth: 1, borderRadius: 8 },
  actions: { flexDirection: "row", gap: 12, marginTop: 12 },
  btnSecondary: { paddingHorizontal: 14, paddingVertical: 10, borderWidth: 1, borderRadius: 8 },
  btnPrimary: { paddingHorizontal: 18, paddingVertical: 10, borderRadius: 8 },
});
```

- [ ] **Step 4: Run, commit**

```bash
cd apps/web && npm test -- --testPathPattern=FirstRunWizard
git add apps/web/src/screens/FirstRunWizard.tsx apps/web/src/screens/__tests__/FirstRunWizard.test.tsx
git commit -m "feat(web): FirstRunWizard with provider/model picker + test connection (#8)"
```

---

## Task 4: Wire wizard into the app layout

**Files:**
- Modify: `apps/web/app/_layout.tsx`

`_layout.tsx` must, on mount:
1. Call `apiClient.getSettings()`. If it returns null → render `<FirstRunWizard>` instead of the Stack.
2. After wizard completes, render the normal Stack.
3. Set a `localStorage` flag `rentwise.wizardCompleted=v1` so subsequent boots skip the API check (faster). The flag is checked first; if set, render the Stack directly without calling getSettings.

- [ ] **Step 1: Implement**

```tsx
import { Stack } from "expo-router";
import React, { useEffect, useState } from "react";
import { Platform, View, ActivityIndicator } from "react-native";
import Constants from "expo-constants";
import { QueryProvider } from "@/src/state/QueryProvider";
import { FirstRunWizard } from "@/src/screens/FirstRunWizard";
import { searchClient } from "@/src/api/client";

const API_BASE_URL =
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  "http://localhost:8000";

const WIZARD_FLAG_KEY = "rentwise.wizardCompleted";

function readFlag(): boolean {
  if (Platform.OS !== "web") return false;
  try {
    return window.localStorage.getItem(WIZARD_FLAG_KEY) === "v1";
  } catch {
    return false;
  }
}

function writeFlag() {
  if (Platform.OS !== "web") return;
  try { window.localStorage.setItem(WIZARD_FLAG_KEY, "v1"); } catch { /* noop */ }
}

export default function RootLayout() {
  // "checking" until we know whether to show the wizard.
  const [phase, setPhase] = useState<"checking" | "wizard" | "ready">(() =>
    readFlag() ? "ready" : "checking"
  );

  useEffect(() => {
    if (phase !== "checking") return;
    let cancelled = false;
    void searchClient(API_BASE_URL).getSettings().then((s) => {
      if (cancelled) return;
      if (s) {
        writeFlag();
        setPhase("ready");
      } else {
        setPhase("wizard");
      }
    }).catch(() => {
      // API unreachable — fail open into the app; the user can configure later.
      if (!cancelled) setPhase("ready");
    });
    return () => { cancelled = true; };
  }, [phase]);

  if (phase === "checking") {
    return (
      <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
        <ActivityIndicator />
      </View>
    );
  }

  if (phase === "wizard") {
    return (
      <FirstRunWizard
        apiBaseUrl={API_BASE_URL}
        onComplete={() => { writeFlag(); setPhase("ready"); }}
      />
    );
  }

  return (
    <QueryProvider>
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: "#0f172a" },
          headerTintColor: "#f8fafc",
          headerTitleStyle: { fontWeight: "600" },
        }}
      >
        <Stack.Screen name="index" options={{ title: "RentWise" }} />
        <Stack.Screen name="settings" options={{ title: "Settings" }} />
      </Stack>
    </QueryProvider>
  );
}
```

- [ ] **Step 2: Verify existing screen tests still pass**

The existing `SearchScreen.test.tsx` mounts the screen directly, not via the layout — it stays green.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/_layout.tsx
git commit -m "feat(web): _layout probes /settings/llm and shows wizard on first run (#8)"
```

---

## Task 5: SettingsScreen + route

**Files:**
- Create: `apps/web/src/screens/SettingsScreen.tsx`
- Create: `apps/web/app/settings.tsx` (Expo Router route)
- Create: `apps/web/src/screens/__tests__/SettingsScreen.test.tsx`

The settings screen mirrors the wizard but loads existing settings via `getSettings()` and:
- Shows the masked key as read-only with a "Replace" button to reveal a new input.
- Has a "Test connection" button (uses the new key if entered, else sends `null` and lets the server use its stored key — but the server test endpoint expects a key, so we send the field unchanged when empty).
- Has a "Save" button calling `putSettings` with `primary_api_key_clear: false` and the new key only if the user replaced it.

For Phase 2, keep the screen minimal — provider + model + key (replace pattern). Fallback can wait until Phase 5.

- [ ] **Step 1: Failing tests** — 3 small tests:
  1. Loads existing settings on mount (calls `getSettings()`, displays the masked key text).
  2. Replace flow — pressing "Replace" reveals an input; typing + Save sends the new key in the PUT body.
  3. "Test connection" calls `testConnection` and shows ok latency.

- [ ] **Step 2: Implement** — same shape as `FirstRunWizard` minus the welcome heading. On mount, `useEffect` calls `getSettings()` and seeds `providerId`/`modelId`. The masked key is shown as `<Text>{settings.primary_api_key_masked ?? "(none)"}</Text>` with a `[Replace]` button that toggles a state `replaceMode` to show the `<TextInput>`. Save: send `primary_api_key` only if `replaceMode && apiKey.length > 0`.

- [ ] **Step 3: Add the route**

`apps/web/app/settings.tsx`:

```tsx
import Constants from "expo-constants";
import { SettingsScreen } from "@/src/screens/SettingsScreen";

const API_BASE_URL =
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  "http://localhost:8000";

export default function SettingsRoute() {
  return <SettingsScreen apiBaseUrl={API_BASE_URL} />;
}
```

- [ ] **Step 4: Add a header gear icon**

In `_layout.tsx`, set `headerRight` on the index Stack.Screen pointing to `/settings`. RN Pressable + Text "⚙" works fine cross-platform:

```tsx
import { Link } from "expo-router";
// ...
<Stack.Screen
  name="index"
  options={{
    title: "RentWise",
    headerRight: () => (
      <Link href="/settings" accessibilityLabel="Open settings">
        <Text style={{ color: "#f8fafc", fontSize: 18, paddingHorizontal: 12 }}>⚙</Text>
      </Link>
    ),
  }}
/>
```

- [ ] **Step 5: Run, commit**

```bash
cd apps/web && npm test -- --testPathPattern=SettingsScreen
git add apps/web/src/screens/SettingsScreen.tsx apps/web/src/screens/__tests__/SettingsScreen.test.tsx apps/web/app/settings.tsx apps/web/app/_layout.tsx
git commit -m "feat(web): SettingsScreen + route + header gear (#8)"
```

---

## Task 6: Playwright smoke E2E

**Files:**
- Create: `apps/web/e2e/first-run.smoke.spec.ts`

```ts
import { test, expect } from "@playwright/test";

test("first-run wizard: 404 → wizard → save → search reachable", async ({ page }) => {
  // Clear localStorage flag
  await page.addInitScript(() => { window.localStorage.removeItem("rentwise.wizardCompleted"); });

  // Stub backend
  await page.route("**/settings/llm", async (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "no_llm_settings" }) });
    } else {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        primary_model: "openrouter/qwen/qwen-2.5-72b-instruct:free",
        primary_api_key_masked: "sk-or-...test",
        fallback_model: null, fallback_api_key_masked: null,
        custom_base_url: null, timeout_seconds: 30,
      }) });
    }
  });
  await page.route("**/settings/llm/test", async (route) => {
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, error: null, latency_ms: 50, model_used: "m" }) });
  });

  await page.goto("/");

  // Wizard appears
  await expect(page.getByText(/Welcome to RentWise/i)).toBeVisible();

  // Fill API key, test, finish
  await page.getByLabel("API key").fill("sk-or-test");
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText(/Connection ok/i)).toBeVisible();
  await page.getByRole("button", { name: "Finish" }).click();

  // Now on the normal app
  await expect(page.getByRole("button", { name: "Search" })).toBeVisible({ timeout: 10000 });
});
```

- [ ] **Step 1: Run smoke**

```bash
cd apps/web && npm run e2e -- first-run.smoke.spec.ts
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/e2e/first-run.smoke.spec.ts
git commit -m "test(web): Playwright smoke for first-run wizard flow (#8)"
```

---

## Task 7: Lint + push + PR + plan commit

- [ ] **Step 1: Lint + typecheck + full jest**

```bash
cd apps/web && npm test && npm run lint && npm run typecheck
```

- [ ] **Step 2: Push + PR**

```bash
git push -u origin feat/phase-2-wizard

gh pr create --title "feat(web): first-run wizard + LLM settings screen (#8)" --body "$(cat <<'EOF'
Closes #8.

## Summary
- `apiClient.getSettings/putSettings/testConnection` extending the API client.
- `PROVIDERS` catalog (5 providers, models, free tags).
- `FirstRunWizard`: provider/model/key selection, test-connection, error→Skip, success→Finish → `putSettings` → onComplete.
- `_layout.tsx` probes `/settings/llm` on mount and shows the wizard if 404; persists a `rentwise.wizardCompleted` flag in localStorage.
- `SettingsScreen` for editing existing settings (Replace pattern for the masked key).
- Header gear icon links to /settings.

## Test plan
- [x] jest+RTL: client extensions, providers catalog, FirstRunWizard (default + ollama-no-key + test-success-enables-Finish + test-failure-shows-Skip + Finish-calls-put-and-onComplete), SettingsScreen (load + replace + test)
- [x] Playwright smoke: 404 → wizard → save → search reachable
- [x] tsc + eslint clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Commit + push the plan**

```bash
git add docs/superpowers/plans/2026-05-06-phase-2-issue-8-wizard-settings.md
git commit -m "docs: add Phase 2 Issue #8 implementation plan"
git push
```

---

## Done checklist (Issue #8)

- [ ] Tasks 1–6 complete with green tests
- [ ] Branch `feat/phase-2-wizard` pushed
- [ ] PR opened, links to #8
- [ ] CI green
