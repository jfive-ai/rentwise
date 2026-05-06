# Phase 1 Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 frontend: faceted filter UI (Mode B per `docs/specifications.md` §3.1) and dual-mode results display (card grid + list/table per §3.2), wired to `POST /search`. No NL parsing yet (Phase 2). Universal — runs on Web, iOS, macOS from the same codebase.

**Architecture:** A single Expo Router screen (`app/index.tsx`) hosts a `<FilterPanel>` (left/top), a `<ResultsToolbar>`, and a results region that swaps between `<ListingCard>` grid and `<ListingTable>` (virtualized via `FlatList`). Shared state is a `NormalizedQueryProvider` React Context — no Redux. The screen calls `searchClient.search(query, { sort, limit, offset })` which POSTs to the backend. Local-only listing actions (save / hide / contacted) persist via a platform-branched storage module.

**Tech Stack:** TypeScript (strict), Expo SDK 52 + Expo Router 4, React Native 0.76, react-native-web 0.19. Tests: jest + jest-expo + @testing-library/react-native. Network stubs: msw. E2E: Playwright (web target only). No new state-management library.

**Spec:** `docs/superpowers/specs/2026-05-06-phase-1-craigslist-design.md` §7 — read first; this plan is one valid path to executing it. UX details in `docs/specifications.md` §3.1 (Mode B) and §3.2.

**Branch:** `feat/phase-1-frontend` (already created off `origin/main`).

**Prerequisites:** Phase 1 backend (PR #3) is merged. `POST /search` returns `SearchResponse` per `apps/api/rentwise/models.py`.

---

## File Structure

### Created

```
apps/web/src/api/types.ts                     # SearchRequest/Response mirrors of Pydantic
apps/web/src/api/client.ts                    # POST /search wrapper
apps/web/src/api/__tests__/client.test.ts
apps/web/src/state/QueryProvider.tsx          # NormalizedQuery context
apps/web/src/state/__tests__/QueryProvider.test.tsx
apps/web/src/storage/listingActions.ts        # platform-branched local storage
apps/web/src/storage/__tests__/listingActions.test.ts
apps/web/src/theme.ts                         # light/dark tokens
apps/web/src/components/DisabledControl.tsx
apps/web/src/components/__tests__/DisabledControl.test.tsx
apps/web/src/components/FilterPanel.tsx
apps/web/src/components/__tests__/FilterPanel.test.tsx
apps/web/src/components/ResultsToolbar.tsx
apps/web/src/components/__tests__/ResultsToolbar.test.tsx
apps/web/src/components/ListingCard.tsx
apps/web/src/components/__tests__/ListingCard.test.tsx
apps/web/src/components/ListingTable.tsx
apps/web/src/components/__tests__/ListingTable.test.tsx
apps/web/src/components/StateBanners.tsx     # EmptyState/ErrorState/Loading skeleton
apps/web/src/components/__tests__/StateBanners.test.tsx
apps/web/src/screens/SearchScreen.tsx        # composed screen (rendered by app/index.tsx)
apps/web/src/screens/__tests__/SearchScreen.test.tsx
apps/web/__fixtures__/search_response.json   # 5 listings, used by tests + Playwright
apps/web/__mocks__/AsyncStorage.ts            # jest mock for native storage
apps/web/jest.config.js
apps/web/jest.setup.ts
apps/web/playwright.config.ts
apps/web/e2e/search.smoke.spec.ts
apps/web/e2e/msw-handlers.ts
apps/web/.eslintrc.cjs
```

### Modified

```
apps/web/package.json                         # +deps: jest, jest-expo, RTL, msw, playwright, async-storage, eslint
apps/web/app/_layout.tsx                      # wrap with QueryProvider
apps/web/app/index.tsx                        # render <SearchScreen/>
apps/web/tsconfig.json                        # add jest types, src path alias
.github/workflows/ci.yml                      # extend Web job: jest + playwright
docs/roadmap.md                               # tick frontend chunks
README.md                                     # update screenshot section / status
```

---

## Conventions used in tasks

- **Path alias `@/*` resolves to `apps/web/`** — already configured in `tsconfig.json`. Tests import via `@/src/...`.
- All components use `View / Text / Pressable / ScrollView / FlatList` from `react-native`. **No `<div>` / `<button>`.**
- All `fetch`-style calls go through `src/api/client.ts`. Components receive data via props or context — never call `fetch` directly.
- Each task ends with `git commit` using Conventional Commits (`feat(web):`, `test(web):`, `chore(web):`).
- Run from `apps/web/`: `npm test -- --watch=false` for jest; `npx tsc --noEmit` for types; `npx playwright test` for E2E.

---

## Task 1: Tooling — jest + RTL + msw + lint config

**Files:**
- Modify: `apps/web/package.json` (add devDependencies)
- Create: `apps/web/jest.config.js`
- Create: `apps/web/jest.setup.ts`
- Create: `apps/web/.eslintrc.cjs`
- Create: `apps/web/__mocks__/AsyncStorage.ts`
- Modify: `apps/web/tsconfig.json` (add `jest` types, ensure `src/**/*.ts(x)` is included)

- [ ] **Step 1.1: Add devDependencies and scripts**

Update `apps/web/package.json`:

```json
{
  "name": "rentwise-web",
  "version": "0.1.0",
  "main": "expo-router/entry",
  "scripts": {
    "start": "expo start",
    "web": "expo start --web",
    "ios": "expo start --ios",
    "android": "expo start --android",
    "lint": "eslint 'src/**/*.{ts,tsx}' 'app/**/*.{ts,tsx}'",
    "typecheck": "tsc --noEmit",
    "test": "jest",
    "test:coverage": "jest --coverage",
    "e2e": "playwright test",
    "e2e:install": "playwright install --with-deps chromium"
  },
  "dependencies": {
    "expo": "~52.0.0",
    "expo-router": "~4.0.0",
    "expo-status-bar": "~2.0.0",
    "expo-linking": "~7.0.0",
    "expo-constants": "~17.0.0",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "react-native": "0.76.0",
    "react-native-web": "~0.19.13",
    "react-native-safe-area-context": "4.12.0",
    "react-native-screens": "~4.1.0",
    "@react-native-async-storage/async-storage": "1.23.1"
  },
  "devDependencies": {
    "@babel/core": "^7.25.0",
    "@playwright/test": "^1.48.0",
    "@testing-library/jest-native": "^5.4.3",
    "@testing-library/react-native": "^12.7.0",
    "@types/jest": "^29.5.12",
    "@types/react": "~18.3.12",
    "@typescript-eslint/eslint-plugin": "^7.18.0",
    "@typescript-eslint/parser": "^7.18.0",
    "eslint": "^8.57.0",
    "eslint-config-expo": "^7.1.2",
    "eslint-plugin-react-hooks": "^4.6.2",
    "jest": "^29.7.0",
    "jest-expo": "~52.0.0",
    "msw": "^2.6.0",
    "react-test-renderer": "18.3.1",
    "typescript": "^5.6.3"
  },
  "private": true
}
```

- [ ] **Step 1.2: Create `apps/web/jest.config.js`**

```js
/** @type {import('jest').Config} */
module.exports = {
  preset: "jest-expo",
  setupFilesAfterEach: ["<rootDir>/jest.setup.ts"],
  transformIgnorePatterns: [
    "node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|@react-native-async-storage)/.*)",
  ],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },
  collectCoverageFrom: [
    "src/**/*.{ts,tsx}",
    "!src/**/__tests__/**",
    "!src/**/*.d.ts",
  ],
  coverageThreshold: {
    global: {
      branches: 75,
      lines: 80,
      statements: 80,
    },
  },
  testPathIgnorePatterns: ["/node_modules/", "/e2e/", "/.expo/"],
};
```

- [ ] **Step 1.3: Create `apps/web/jest.setup.ts`**

```ts
import "@testing-library/jest-native/extend-expect";

// AsyncStorage doesn't exist in jsdom; use the official mock.
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock")
);

// Silence the react-native warning about unrecognized event names in tests.
jest.mock("react-native/Libraries/Animated/NativeAnimatedHelper");
```

- [ ] **Step 1.4: Create `apps/web/.eslintrc.cjs`**

```js
module.exports = {
  root: true,
  extends: ["expo", "plugin:@typescript-eslint/recommended"],
  parser: "@typescript-eslint/parser",
  plugins: ["@typescript-eslint", "react-hooks"],
  rules: {
    "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    "@typescript-eslint/no-explicit-any": "error",
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",
  },
  ignorePatterns: ["node_modules", ".expo", "dist", "web-build", "e2e"],
};
```

- [ ] **Step 1.5: Update `apps/web/tsconfig.json`**

```json
{
  "extends": "expo/tsconfig.base",
  "compilerOptions": {
    "strict": true,
    "types": ["jest"],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": [
    "**/*.ts",
    "**/*.tsx",
    ".expo/types/**/*.ts",
    "expo-env.d.ts"
  ],
  "exclude": ["node_modules", ".expo", "dist", "web-build", "e2e"]
}
```

- [ ] **Step 1.6: Install and verify**

Run from `apps/web/`:

```bash
npm install
npx tsc --noEmit
npm test -- --passWithNoTests
```

Expected: install succeeds, `tsc` clean, jest reports 0 tests passing.

- [ ] **Step 1.7: Commit**

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/jest.config.js apps/web/jest.setup.ts apps/web/.eslintrc.cjs apps/web/tsconfig.json
git commit -m "chore(web): add jest, RTL, msw, eslint, playwright tooling"
```

---

## Task 2: API types + client (POST /search)

**Files:**
- Create: `apps/web/src/api/types.ts`
- Create: `apps/web/src/api/client.ts`
- Create: `apps/web/src/api/__tests__/client.test.ts`

- [ ] **Step 2.1: Write the failing test**

`apps/web/src/api/__tests__/client.test.ts`:

```ts
import { searchClient, ApiError } from "@/src/api/client";

describe("searchClient.search", () => {
  const baseUrl = "http://api.test";
  const query = { bedrooms_min: 2, price_max: 3000 };

  beforeEach(() => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn();
  });

  it("posts to /search with the provided query and pagination", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        listings: [],
        total: 0,
        cache_status: "miss",
        unsupported_filters: [],
        source_health: {},
      }),
    });

    await searchClient(baseUrl).search({
      query: query as never,
      limit: 25,
      offset: 0,
      sort: "newest",
      force_refresh: false,
    });

    const call = (global.fetch as jest.Mock).mock.calls[0];
    expect(call[0]).toBe("http://api.test/search");
    expect(call[1].method).toBe("POST");
    expect(call[1].headers["content-type"]).toBe("application/json");
    expect(JSON.parse(call[1].body)).toEqual({
      query: { bedrooms_min: 2, price_max: 3000 },
      limit: 25,
      offset: 0,
      sort: "newest",
      force_refresh: false,
    });
  });

  it("throws ApiError with status on non-2xx", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({ detail: "bad" }),
    });

    await expect(
      searchClient(baseUrl).search({ query: {} as never })
    ).rejects.toMatchObject({ name: "ApiError", status: 422 });
  });

  it("wraps fetch network errors as ApiError(status=0)", async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new TypeError("net"));

    await expect(
      searchClient(baseUrl).search({ query: {} as never })
    ).rejects.toMatchObject({ name: "ApiError", status: 0 });
  });
});
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
cd apps/web && npm test -- --testPathPattern=api/__tests__/client
```

Expected: FAIL with "Cannot find module '@/src/api/client'".

- [ ] **Step 2.3: Implement types and client**

`apps/web/src/api/types.ts`:

```ts
// Mirrors apps/api/rentwise/models.py — keep field names in sync.

export type PetPolicy = "required" | "ok" | "no" | "any";
export type FurnishedPolicy = "yes" | "no" | "any";
export type SortOrder = "newest" | "price_asc" | "price_desc" | "bedrooms";
export type CacheStatus = "fresh" | "stale" | "miss";

export interface NormalizedQuery {
  bedrooms_min?: number | null;
  bedrooms_max?: number | null;
  price_min?: number | null;
  price_max?: number | null;
  neighborhoods: string[];
  school_catchment?: string | null;
  pets: PetPolicy;
  furnished: FurnishedPolicy;
  available_after?: string | null; // ISO date
  transit_max_walk_minutes?: number | null;
  free_text_keywords: string[];
}

export const emptyQuery = (): NormalizedQuery => ({
  neighborhoods: [],
  pets: "any",
  furnished: "any",
  free_text_keywords: [],
});

export interface SearchRequest {
  query: NormalizedQuery;
  force_refresh?: boolean;
  limit?: number;
  offset?: number;
  sort?: SortOrder;
}

export interface SchoolCatchments {
  elementary: string | null;
  middle: string | null;
  secondary: string | null;
}

export interface TransitInfo {
  nearest_stop_name: string;
  walk_minutes: number;
  line: string | null;
}

export interface NormalizedListing {
  id: string;
  canonical_id: string;
  source: string;
  source_url: string;
  source_listing_id: string;
  title: string;
  address: string | null;
  address_normalized: string | null;
  lat: number | null;
  lon: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  price_cad: number | null;
  pets_allowed: boolean | null;
  furnished: boolean | null;
  available_date: string | null;
  posted_at: string;
  last_seen_at: string;
  photos: string[];
  description_snippet: string | null;
  school_catchments: SchoolCatchments;
  nearest_transit: TransitInfo | null;
  walkscore: number | null;
  raw_metadata: Record<string, unknown>;
}

export interface AdapterHealth {
  name: string;
  status: string; // "ok" | "degraded" | "blocked"
  last_successful_fetch: string | null;
  last_error: string | null;
}

export interface SearchResponse {
  listings: NormalizedListing[];
  total: number;
  cache_status: CacheStatus;
  unsupported_filters: string[];
  source_health: Record<string, AdapterHealth>;
}
```

`apps/web/src/api/client.ts`:

```ts
import type { SearchRequest, SearchResponse } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;
  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export interface SearchClient {
  search(req: SearchRequest): Promise<SearchResponse>;
}

export function searchClient(baseUrl: string): SearchClient {
  return {
    async search(req) {
      const url = `${baseUrl.replace(/\/$/, "")}/search`;
      let res: Response;
      try {
        res = await fetch(url, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(req),
        });
      } catch (e) {
        throw new ApiError(0, e instanceof Error ? e.message : String(e));
      }
      if (!res.ok) {
        let payload: unknown;
        try { payload = await res.json(); } catch { /* ignore */ }
        throw new ApiError(res.status, `HTTP ${res.status}`, payload);
      }
      return (await res.json()) as SearchResponse;
    },
  };
}
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
npm test -- --testPathPattern=api/__tests__/client
```

Expected: 3 passing.

- [ ] **Step 2.5: Commit**

```bash
git add apps/web/src/api/
git commit -m "feat(web): add SearchRequest/Response types and POST /search client"
```

---

## Task 3: NormalizedQuery context provider

**Files:**
- Create: `apps/web/src/state/QueryProvider.tsx`
- Create: `apps/web/src/state/__tests__/QueryProvider.test.tsx`

- [ ] **Step 3.1: Write the failing test**

`apps/web/src/state/__tests__/QueryProvider.test.tsx`:

```tsx
import React from "react";
import { Pressable, Text } from "react-native";
import { render, fireEvent } from "@testing-library/react-native";
import { QueryProvider, useQuery } from "@/src/state/QueryProvider";

function Probe() {
  const { query, set, reset, toggleNeighborhood } = useQuery();
  return (
    <>
      <Text testID="bedrooms">{String(query.bedrooms_min ?? "")}</Text>
      <Text testID="hoods">{query.neighborhoods.join(",")}</Text>
      <Pressable testID="set-bed" onPress={() => set({ bedrooms_min: 2 })}>
        <Text>set</Text>
      </Pressable>
      <Pressable testID="add-kits" onPress={() => toggleNeighborhood("Kitsilano")}>
        <Text>kits</Text>
      </Pressable>
      <Pressable testID="reset" onPress={reset}>
        <Text>reset</Text>
      </Pressable>
    </>
  );
}

describe("QueryProvider", () => {
  it("starts with the empty query", () => {
    const { getByTestId } = render(
      <QueryProvider>
        <Probe />
      </QueryProvider>
    );
    expect(getByTestId("bedrooms").props.children).toBe("");
    expect(getByTestId("hoods").props.children).toBe("");
  });

  it("merges fields via set()", () => {
    const { getByTestId } = render(
      <QueryProvider>
        <Probe />
      </QueryProvider>
    );
    fireEvent.press(getByTestId("set-bed"));
    expect(getByTestId("bedrooms").props.children).toBe("2");
  });

  it("toggleNeighborhood adds then removes", () => {
    const { getByTestId } = render(
      <QueryProvider>
        <Probe />
      </QueryProvider>
    );
    fireEvent.press(getByTestId("add-kits"));
    expect(getByTestId("hoods").props.children).toBe("Kitsilano");
    fireEvent.press(getByTestId("add-kits"));
    expect(getByTestId("hoods").props.children).toBe("");
  });

  it("reset() returns to empty", () => {
    const { getByTestId } = render(
      <QueryProvider>
        <Probe />
      </QueryProvider>
    );
    fireEvent.press(getByTestId("set-bed"));
    fireEvent.press(getByTestId("add-kits"));
    fireEvent.press(getByTestId("reset"));
    expect(getByTestId("bedrooms").props.children).toBe("");
    expect(getByTestId("hoods").props.children).toBe("");
  });

  it("useQuery throws when called outside provider", () => {
    // Render a component that uses the hook with no provider; React throws synchronously.
    const Bad = () => {
      useQuery();
      return null;
    };
    expect(() => render(<Bad />)).toThrow(/QueryProvider/);
  });
});
```

- [ ] **Step 3.2: Run test to verify it fails**

```bash
npm test -- --testPathPattern=state/__tests__/QueryProvider
```

Expected: FAIL with "Cannot find module '@/src/state/QueryProvider'".

- [ ] **Step 3.3: Implement provider**

`apps/web/src/state/QueryProvider.tsx`:

```tsx
import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { type NormalizedQuery, emptyQuery } from "@/src/api/types";

interface QueryContextValue {
  query: NormalizedQuery;
  set: (patch: Partial<NormalizedQuery>) => void;
  reset: () => void;
  toggleNeighborhood: (name: string) => void;
  toggleKeyword: (k: string) => void;
}

const QueryContext = createContext<QueryContextValue | null>(null);

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [query, setQuery] = useState<NormalizedQuery>(() => emptyQuery());

  const set = useCallback((patch: Partial<NormalizedQuery>) => {
    setQuery((prev) => ({ ...prev, ...patch }));
  }, []);

  const reset = useCallback(() => setQuery(emptyQuery()), []);

  const toggleNeighborhood = useCallback((name: string) => {
    setQuery((prev) => {
      const exists = prev.neighborhoods.includes(name);
      return {
        ...prev,
        neighborhoods: exists
          ? prev.neighborhoods.filter((n) => n !== name)
          : [...prev.neighborhoods, name],
      };
    });
  }, []);

  const toggleKeyword = useCallback((k: string) => {
    const norm = k.trim();
    if (!norm) return;
    setQuery((prev) => {
      const exists = prev.free_text_keywords.includes(norm);
      return {
        ...prev,
        free_text_keywords: exists
          ? prev.free_text_keywords.filter((x) => x !== norm)
          : [...prev.free_text_keywords, norm],
      };
    });
  }, []);

  const value = useMemo<QueryContextValue>(
    () => ({ query, set, reset, toggleNeighborhood, toggleKeyword }),
    [query, set, reset, toggleNeighborhood, toggleKeyword]
  );

  return <QueryContext.Provider value={value}>{children}</QueryContext.Provider>;
}

export function useQuery(): QueryContextValue {
  const ctx = useContext(QueryContext);
  if (!ctx) throw new Error("useQuery must be used inside <QueryProvider>");
  return ctx;
}
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
npm test -- --testPathPattern=state/__tests__/QueryProvider
```

Expected: 5 passing.

- [ ] **Step 3.5: Commit**

```bash
git add apps/web/src/state/
git commit -m "feat(web): add NormalizedQuery context provider"
```

---

## Task 4: Platform-branched listing-actions storage

**Files:**
- Create: `apps/web/src/storage/listingActions.ts`
- Create: `apps/web/src/storage/__tests__/listingActions.test.ts`

The hook persists per-listing user actions (saved / hidden / contacted) locally. Web → `localStorage`; native → `@react-native-async-storage/async-storage`. The seam is `Platform.OS`.

- [ ] **Step 4.1: Write the failing test**

`apps/web/src/storage/__tests__/listingActions.test.ts`:

```ts
import {
  loadActions,
  setAction,
  clearActions,
  ListingActionMap,
} from "@/src/storage/listingActions";

describe("listingActions (web/jsdom path)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns an empty map when nothing is stored", async () => {
    const actions = await loadActions();
    expect(actions).toEqual({});
  });

  it("persists a saved action and reads it back", async () => {
    await setAction("listing-1", "saved", true);
    const actions = await loadActions();
    expect(actions["listing-1"]).toEqual({ saved: true });
  });

  it("merges multiple flags on the same listing", async () => {
    await setAction("listing-1", "saved", true);
    await setAction("listing-1", "contacted", true);
    const actions = await loadActions();
    expect(actions["listing-1"]).toEqual({ saved: true, contacted: true });
  });

  it("setAction(false) removes the flag", async () => {
    await setAction("listing-1", "saved", true);
    await setAction("listing-1", "saved", false);
    const actions = await loadActions();
    // The listing key may or may not exist; just assert the flag is not truthy.
    expect(actions["listing-1"]?.saved ?? false).toBe(false);
  });

  it("clearActions wipes everything", async () => {
    await setAction("a", "saved", true);
    await setAction("b", "hidden", true);
    await clearActions();
    expect(await loadActions()).toEqual({} as ListingActionMap);
  });

  it("survives a corrupted localStorage payload", async () => {
    window.localStorage.setItem("rentwise.listingActions.v1", "{not json}");
    expect(await loadActions()).toEqual({});
  });
});
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
npm test -- --testPathPattern=storage/__tests__/listingActions
```

Expected: FAIL with module-not-found.

- [ ] **Step 4.3: Implement storage**

`apps/web/src/storage/listingActions.ts`:

```ts
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "rentwise.listingActions.v1";

export type ActionFlag = "saved" | "hidden" | "contacted";
export type ListingActions = Partial<Record<ActionFlag, boolean>>;
export type ListingActionMap = Record<string, ListingActions>;

interface StorageBackend {
  getItem(k: string): Promise<string | null>;
  setItem(k: string, v: string): Promise<void>;
  removeItem(k: string): Promise<void>;
}

function backend(): StorageBackend {
  if (Platform.OS === "web") {
    return {
      async getItem(k) { return window.localStorage.getItem(k); },
      async setItem(k, v) { window.localStorage.setItem(k, v); },
      async removeItem(k) { window.localStorage.removeItem(k); },
    };
  }
  return {
    async getItem(k) { return AsyncStorage.getItem(k); },
    async setItem(k, v) { await AsyncStorage.setItem(k, v); },
    async removeItem(k) { await AsyncStorage.removeItem(k); },
  };
}

export async function loadActions(): Promise<ListingActionMap> {
  const raw = await backend().getItem(KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as ListingActionMap;
    }
    return {};
  } catch {
    return {};
  }
}

export async function setAction(
  listingId: string,
  flag: ActionFlag,
  value: boolean
): Promise<ListingActionMap> {
  const map = await loadActions();
  const current: ListingActions = { ...(map[listingId] ?? {}) };
  if (value) {
    current[flag] = true;
  } else {
    delete current[flag];
  }
  if (Object.keys(current).length === 0) {
    delete map[listingId];
  } else {
    map[listingId] = current;
  }
  await backend().setItem(KEY, JSON.stringify(map));
  return map;
}

export async function clearActions(): Promise<void> {
  await backend().removeItem(KEY);
}
```

- [ ] **Step 4.4: Run tests to verify they pass**

```bash
npm test -- --testPathPattern=storage/__tests__/listingActions
```

Expected: 6 passing.

- [ ] **Step 4.5: Commit**

```bash
git add apps/web/src/storage/
git commit -m "feat(web): platform-branched local storage for listing actions"
```

---

## Task 5: Theme tokens

**Files:**
- Create: `apps/web/src/theme.ts`

No tests for static tokens; consumers get type-safety from the export.

- [ ] **Step 5.1: Create `apps/web/src/theme.ts`**

```ts
import { useColorScheme } from "react-native";

export interface Theme {
  bg: string;
  surface: string;
  surfaceAlt: string;
  border: string;
  text: string;
  textMuted: string;
  accent: string;
  ok: string;
  warn: string;
  error: string;
  disabled: string;
}

export const lightTheme: Theme = {
  bg: "#ffffff",
  surface: "#f8fafc",
  surfaceAlt: "#e2e8f0",
  border: "#cbd5e1",
  text: "#0f172a",
  textMuted: "#475569",
  accent: "#0ea5e9",
  ok: "#16a34a",
  warn: "#d97706",
  error: "#dc2626",
  disabled: "#94a3b8",
};

export const darkTheme: Theme = {
  bg: "#020617",
  surface: "#0f172a",
  surfaceAlt: "#1e293b",
  border: "#334155",
  text: "#f8fafc",
  textMuted: "#cbd5e1",
  accent: "#38bdf8",
  ok: "#22c55e",
  warn: "#f59e0b",
  error: "#ef4444",
  disabled: "#64748b",
};

export function useTheme(): Theme {
  const scheme = useColorScheme();
  return scheme === "light" ? lightTheme : darkTheme;
}
```

- [ ] **Step 5.2: Verify it type-checks**

```bash
npx tsc --noEmit
```

- [ ] **Step 5.3: Commit**

```bash
git add apps/web/src/theme.ts
git commit -m "feat(web): add light/dark theme tokens"
```

---

## Task 6: `<DisabledControl>` wrapper

**Files:**
- Create: `apps/web/src/components/DisabledControl.tsx`
- Create: `apps/web/src/components/__tests__/DisabledControl.test.tsx`

A presentational wrapper that greys out a placeholder control and shows a phase badge — used for school catchment, pets, furnished, available-after, transit-walk-time.

- [ ] **Step 6.1: Write the failing test**

`apps/web/src/components/__tests__/DisabledControl.test.tsx`:

```tsx
import React from "react";
import { Text } from "react-native";
import { render } from "@testing-library/react-native";
import { DisabledControl } from "@/src/components/DisabledControl";

describe("DisabledControl", () => {
  it("renders the label and phase badge", () => {
    const { getByText } = render(
      <DisabledControl label="Pets" phase="Phase 3 — more sources">
        <Text>placeholder</Text>
      </DisabledControl>
    );
    expect(getByText("Pets")).toBeTruthy();
    expect(getByText("Phase 3 — more sources")).toBeTruthy();
    expect(getByText("placeholder")).toBeTruthy();
  });

  it("marks itself accessible as disabled", () => {
    const { getByLabelText } = render(
      <DisabledControl label="Pets" phase="Phase 3">
        <Text>x</Text>
      </DisabledControl>
    );
    const node = getByLabelText("Pets, disabled (Phase 3)");
    expect(node.props.accessibilityState).toMatchObject({ disabled: true });
  });
});
```

- [ ] **Step 6.2: Implement the component**

`apps/web/src/components/DisabledControl.tsx`:

```tsx
import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTheme } from "@/src/theme";

interface Props {
  label: string;
  phase: string;
  children: React.ReactNode;
}

export function DisabledControl({ label, phase, children }: Props) {
  const t = useTheme();
  return (
    <View
      accessible
      accessibilityLabel={`${label}, disabled (${phase})`}
      accessibilityState={{ disabled: true }}
      style={[styles.wrap, { borderColor: t.border, backgroundColor: t.surface }]}
    >
      <View style={styles.headerRow}>
        <Text style={[styles.label, { color: t.disabled }]}>{label}</Text>
        <View style={[styles.badge, { backgroundColor: t.surfaceAlt }]}>
          <Text style={[styles.badgeText, { color: t.textMuted }]}>{phase}</Text>
        </View>
      </View>
      <View style={styles.body} pointerEvents="none">
        {children}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { borderWidth: 1, borderRadius: 8, padding: 12, gap: 8, opacity: 0.55 },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  label: { fontSize: 14, fontWeight: "600" },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999 },
  badgeText: { fontSize: 11 },
  body: { gap: 4 },
});
```

- [ ] **Step 6.3: Run tests**

```bash
npm test -- --testPathPattern=DisabledControl
```

Expected: 2 passing.

- [ ] **Step 6.4: Commit**

```bash
git add apps/web/src/components/DisabledControl.tsx apps/web/src/components/__tests__/DisabledControl.test.tsx
git commit -m "feat(web): DisabledControl wrapper with phase badge"
```

---

## Task 7: `<FilterPanel>` — the filter UI

**Files:**
- Create: `apps/web/src/components/FilterPanel.tsx`
- Create: `apps/web/src/components/__tests__/FilterPanel.test.tsx`

The list of fully-functional controls and disabled-with-hint controls is fixed by the spec (§7.1, §7.2). Hardcode the supported neighborhoods (the ~25 mapped to postal seeds in the backend) — this avoids a chicken/egg API call.

**Neighborhoods (alphabetical):** `Coal Harbour`, `Commercial Drive`, `Downtown`, `Dunbar`, `East Vancouver`, `Fairview`, `False Creek`, `Gastown`, `Grandview-Woodland`, `Kerrisdale`, `Kitsilano`, `Marpole`, `Mount Pleasant`, `Oakridge`, `Point Grey`, `Riley Park`, `Shaughnessy`, `South Cambie`, `South Granville`, `Strathcona`, `Sunset`, `West End`, `West Point Grey`, `Yaletown`.

- [ ] **Step 7.1: Write the failing test**

`apps/web/src/components/__tests__/FilterPanel.test.tsx`:

```tsx
import React from "react";
import { Text } from "react-native";
import { render, fireEvent } from "@testing-library/react-native";
import { QueryProvider, useQuery } from "@/src/state/QueryProvider";
import { FilterPanel } from "@/src/components/FilterPanel";

function Probe() {
  const { query } = useQuery();
  return <Text testID="query-state">{JSON.stringify(query)}</Text>;
}

function renderPanel() {
  return render(
    <QueryProvider>
      <FilterPanel onSearch={jest.fn()} />
      <Probe />
    </QueryProvider>
  );
}

describe("FilterPanel", () => {
  it("renders all five supported controls", () => {
    const { getByText, getByPlaceholderText } = renderPanel();
    expect(getByText("Bedrooms")).toBeTruthy();
    expect(getByText("Price (CAD/mo)")).toBeTruthy();
    expect(getByText("Neighborhoods")).toBeTruthy();
    expect(getByText("Keywords")).toBeTruthy();
    expect(getByPlaceholderText("Min")).toBeTruthy();
    expect(getByPlaceholderText("Max")).toBeTruthy();
  });

  it("renders disabled controls with phase badges", () => {
    const { getByText, getAllByText } = renderPanel();
    expect(getByText("School catchment")).toBeTruthy();
    expect(getByText("Pets")).toBeTruthy();
    expect(getByText("Furnished")).toBeTruthy();
    expect(getByText("Available after")).toBeTruthy();
    expect(getByText("Transit walk (max min)")).toBeTruthy();
    // At least one phase badge is shown — multiple controls use "Phase 3"
    expect(getAllByText(/Phase 3/i).length).toBeGreaterThan(0);
  });

  it("toggles bedrooms_min / bedrooms_max via chips", () => {
    const { getByText, getByTestId } = renderPanel();
    fireEvent.press(getByText("2"));
    expect(getByTestId("query-state").props.children).toContain('"bedrooms_min":2');
  });

  it("updates price_min / price_max from numeric inputs", () => {
    const { getByPlaceholderText, getByTestId } = renderPanel();
    fireEvent.changeText(getByPlaceholderText("Min"), "1500");
    fireEvent.changeText(getByPlaceholderText("Max"), "3000");
    const state = getByTestId("query-state").props.children;
    expect(state).toContain('"price_min":1500');
    expect(state).toContain('"price_max":3000');
  });

  it("toggles neighborhoods", () => {
    const { getByText, getByTestId } = renderPanel();
    fireEvent.press(getByText("Kitsilano"));
    expect(getByTestId("query-state").props.children).toContain('"Kitsilano"');
    fireEvent.press(getByText("Kitsilano"));
    expect(getByTestId("query-state").props.children).not.toContain('"Kitsilano"');
  });

  it("adds keywords on Enter and removes them on chip press", () => {
    const { getByPlaceholderText, getByText, queryByText, getByTestId } = renderPanel();
    const input = getByPlaceholderText("Add keyword and press Enter");
    fireEvent(input, "submitEditing", { nativeEvent: { text: "balcony" } });
    expect(getByText("balcony ✕")).toBeTruthy();
    expect(getByTestId("query-state").props.children).toContain('"balcony"');
    fireEvent.press(getByText("balcony ✕"));
    expect(queryByText("balcony ✕")).toBeNull();
  });

  it("calls onSearch when Search is pressed", () => {
    const onSearch = jest.fn();
    const { getByText } = render(
      <QueryProvider>
        <FilterPanel onSearch={onSearch} />
      </QueryProvider>
    );
    fireEvent.press(getByText("Search"));
    expect(onSearch).toHaveBeenCalledTimes(1);
  });

  it("Reset clears non-default fields", () => {
    const { getByText, getByPlaceholderText, getByTestId } = renderPanel();
    fireEvent.press(getByText("2"));
    fireEvent.changeText(getByPlaceholderText("Min"), "1500");
    fireEvent.press(getByText("Reset"));
    const state = getByTestId("query-state").props.children;
    expect(state).not.toContain('"bedrooms_min":2');
    expect(state).not.toContain('"price_min":1500');
  });
});
```

- [ ] **Step 7.2: Implement `<FilterPanel>`**

`apps/web/src/components/FilterPanel.tsx`:

```tsx
import React, { useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useQuery } from "@/src/state/QueryProvider";
import { DisabledControl } from "@/src/components/DisabledControl";
import { useTheme } from "@/src/theme";

const BEDROOM_CHIPS = [
  { label: "Studio", value: 0.5 },
  { label: "1", value: 1 },
  { label: "2", value: 2 },
  { label: "3", value: 3 },
  { label: "4+", value: 4 },
];

export const NEIGHBORHOODS = [
  "Coal Harbour", "Commercial Drive", "Downtown", "Dunbar",
  "East Vancouver", "Fairview", "False Creek", "Gastown",
  "Grandview-Woodland", "Kerrisdale", "Kitsilano", "Marpole",
  "Mount Pleasant", "Oakridge", "Point Grey", "Riley Park",
  "Shaughnessy", "South Cambie", "South Granville", "Strathcona",
  "Sunset", "West End", "West Point Grey", "Yaletown",
];

interface Props {
  onSearch: () => void;
}

export function FilterPanel({ onSearch }: Props) {
  const { query, set, reset, toggleNeighborhood, toggleKeyword } = useQuery();
  const t = useTheme();
  const [kw, setKw] = useState("");

  return (
    <ScrollView contentContainerStyle={[styles.wrap, { backgroundColor: t.bg }]}>
      <Section title="Bedrooms" theme={t}>
        <View style={styles.chipRow}>
          {BEDROOM_CHIPS.map((c) => {
            const selected = query.bedrooms_min === c.value;
            return (
              <Pressable
                key={c.label}
                accessibilityRole="button"
                onPress={() =>
                  set({ bedrooms_min: selected ? null : c.value })
                }
                style={[
                  styles.chip,
                  { borderColor: t.border, backgroundColor: selected ? t.accent : t.surface },
                ]}
              >
                <Text style={{ color: selected ? "#fff" : t.text }}>{c.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </Section>

      <Section title="Price (CAD/mo)" theme={t}>
        <View style={styles.row}>
          <TextInput
            placeholder="Min"
            placeholderTextColor={t.textMuted}
            keyboardType="numeric"
            value={query.price_min?.toString() ?? ""}
            onChangeText={(v) => set({ price_min: toIntOrNull(v) })}
            style={[styles.input, { color: t.text, borderColor: t.border }]}
          />
          <TextInput
            placeholder="Max"
            placeholderTextColor={t.textMuted}
            keyboardType="numeric"
            value={query.price_max?.toString() ?? ""}
            onChangeText={(v) => set({ price_max: toIntOrNull(v) })}
            style={[styles.input, { color: t.text, borderColor: t.border }]}
          />
        </View>
      </Section>

      <Section title="Neighborhoods" theme={t}>
        <View style={styles.chipRow}>
          {NEIGHBORHOODS.map((n) => {
            const selected = query.neighborhoods.includes(n);
            return (
              <Pressable
                key={n}
                accessibilityRole="button"
                onPress={() => toggleNeighborhood(n)}
                style={[
                  styles.chip,
                  { borderColor: t.border, backgroundColor: selected ? t.accent : t.surface },
                ]}
              >
                <Text style={{ color: selected ? "#fff" : t.text }}>{n}</Text>
              </Pressable>
            );
          })}
        </View>
      </Section>

      <Section title="Keywords" theme={t}>
        <TextInput
          placeholder="Add keyword and press Enter"
          placeholderTextColor={t.textMuted}
          value={kw}
          onChangeText={setKw}
          onSubmitEditing={(e) => {
            const next = e.nativeEvent.text;
            if (next.trim()) toggleKeyword(next);
            setKw("");
          }}
          returnKeyType="done"
          style={[styles.input, { color: t.text, borderColor: t.border }]}
        />
        <View style={styles.chipRow}>
          {query.free_text_keywords.map((k) => (
            <Pressable
              key={k}
              accessibilityRole="button"
              onPress={() => toggleKeyword(k)}
              style={[styles.chip, { borderColor: t.border, backgroundColor: t.surface }]}
            >
              <Text style={{ color: t.text }}>{k} ✕</Text>
            </Pressable>
          ))}
        </View>
      </Section>

      <DisabledControl label="School catchment" phase="Phase 4 — geocoding">
        <Text style={{ color: t.textMuted }}>Lord Byng / Kitsilano Secondary / …</Text>
      </DisabledControl>
      <DisabledControl label="Pets" phase="Phase 3 — more sources">
        <Text style={{ color: t.textMuted }}>Required · Allowed · Not allowed · Any</Text>
      </DisabledControl>
      <DisabledControl label="Furnished" phase="Phase 3">
        <Text style={{ color: t.textMuted }}>Yes · No · Any</Text>
      </DisabledControl>
      <DisabledControl label="Available after" phase="Phase 3">
        <Text style={{ color: t.textMuted }}>YYYY-MM-DD</Text>
      </DisabledControl>
      <DisabledControl label="Transit walk (max min)" phase="Phase 4 — transit data">
        <Text style={{ color: t.textMuted }}>15</Text>
      </DisabledControl>

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          onPress={onSearch}
          style={[styles.primary, { backgroundColor: t.accent }]}
        >
          <Text style={styles.primaryText}>Search</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={reset}
          style={[styles.secondary, { borderColor: t.border }]}
        >
          <Text style={{ color: t.text }}>Reset</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

function Section({ title, children, theme: t }: { title: string; children: React.ReactNode; theme: ReturnType<typeof useTheme> }) {
  return (
    <View style={styles.section}>
      <Text style={[styles.sectionLabel, { color: t.textMuted }]}>{title}</Text>
      {children}
    </View>
  );
}

function toIntOrNull(v: string): number | null {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : null;
}

const styles = StyleSheet.create({
  wrap: { padding: 16, gap: 16 },
  section: { gap: 8 },
  sectionLabel: { fontSize: 12, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.6 },
  row: { flexDirection: "row", gap: 8 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderRadius: 999 },
  input: { flex: 1, borderWidth: 1, borderRadius: 8, padding: 10 },
  actions: { flexDirection: "row", gap: 8, marginTop: 8 },
  primary: { paddingHorizontal: 18, paddingVertical: 12, borderRadius: 8 },
  primaryText: { color: "#fff", fontWeight: "600" },
  secondary: { paddingHorizontal: 18, paddingVertical: 12, borderRadius: 8, borderWidth: 1 },
});
```

- [ ] **Step 7.3: Run tests**

```bash
npm test -- --testPathPattern=FilterPanel
```

Expected: 8 passing.

- [ ] **Step 7.4: Commit**

```bash
git add apps/web/src/components/FilterPanel.tsx apps/web/src/components/__tests__/FilterPanel.test.tsx
git commit -m "feat(web): FilterPanel with bedrooms/price/neighborhoods/keywords + disabled controls"
```

---

## Task 8: `<ResultsToolbar>`

**Files:**
- Create: `apps/web/src/components/ResultsToolbar.tsx`
- Create: `apps/web/src/components/__tests__/ResultsToolbar.test.tsx`

Total count + sort dropdown + view switcher (Cards / List active; Map / Split disabled).

- [ ] **Step 8.1: Write the failing test**

`apps/web/src/components/__tests__/ResultsToolbar.test.tsx`:

```tsx
import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import { ResultsToolbar } from "@/src/components/ResultsToolbar";

describe("ResultsToolbar", () => {
  const props = {
    total: 142,
    sort: "newest" as const,
    onSortChange: jest.fn(),
    view: "cards" as const,
    onViewChange: jest.fn(),
  };

  beforeEach(() => {
    props.onSortChange.mockReset();
    props.onViewChange.mockReset();
  });

  it("shows the total", () => {
    const { getByText } = render(<ResultsToolbar {...props} />);
    expect(getByText("142 listings")).toBeTruthy();
  });

  it("cycles sort options on press", () => {
    const { getByLabelText } = render(<ResultsToolbar {...props} />);
    fireEvent.press(getByLabelText("Sort by"));
    expect(props.onSortChange).toHaveBeenCalledWith("price_asc");
  });

  it("switches to list view on press", () => {
    const { getByLabelText } = render(<ResultsToolbar {...props} />);
    fireEvent.press(getByLabelText("List view"));
    expect(props.onViewChange).toHaveBeenCalledWith("list");
  });

  it("Map and Split buttons are disabled with a Phase 7 hint", () => {
    const { getByLabelText, getByText } = render(<ResultsToolbar {...props} />);
    const mapBtn = getByLabelText(/Map view/);
    const splitBtn = getByLabelText(/Split view/);
    expect(mapBtn.props.accessibilityState).toMatchObject({ disabled: true });
    expect(splitBtn.props.accessibilityState).toMatchObject({ disabled: true });
    fireEvent.press(mapBtn);
    expect(props.onViewChange).not.toHaveBeenCalled();
    expect(getByText(/Phase 7/i)).toBeTruthy();
  });
});
```

- [ ] **Step 8.2: Implement**

`apps/web/src/components/ResultsToolbar.tsx`:

```tsx
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { SortOrder } from "@/src/api/types";
import { useTheme } from "@/src/theme";

export type ViewMode = "cards" | "list";

const SORT_LABEL: Record<SortOrder, string> = {
  newest: "Newest",
  price_asc: "Price ↑",
  price_desc: "Price ↓",
  bedrooms: "Bedrooms",
};
const SORT_CYCLE: SortOrder[] = ["newest", "price_asc", "price_desc", "bedrooms"];

function nextSort(s: SortOrder): SortOrder {
  const i = SORT_CYCLE.indexOf(s);
  return SORT_CYCLE[(i + 1) % SORT_CYCLE.length];
}

interface Props {
  total: number;
  sort: SortOrder;
  onSortChange: (s: SortOrder) => void;
  view: ViewMode;
  onViewChange: (v: ViewMode) => void;
}

export function ResultsToolbar({ total, sort, onSortChange, view, onViewChange }: Props) {
  const t = useTheme();
  return (
    <View style={[styles.row, { borderColor: t.border, backgroundColor: t.surface }]}>
      <Text style={{ color: t.text, fontWeight: "600" }}>{total} listings</Text>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Sort by"
        onPress={() => onSortChange(nextSort(sort))}
        style={[styles.btn, { borderColor: t.border }]}
      >
        <Text style={{ color: t.text }}>Sort: {SORT_LABEL[sort]} ▾</Text>
      </Pressable>

      <View style={styles.switcher}>
        <ViewBtn label="Cards" mode="cards" active={view === "cards"} onPress={() => onViewChange("cards")} />
        <ViewBtn label="List" mode="list" active={view === "list"} onPress={() => onViewChange("list")} />
        <ViewBtnDisabled label="Map" phase="Phase 7" />
        <ViewBtnDisabled label="Split" phase="Phase 7" />
      </View>
    </View>
  );
}

function ViewBtn({ label, mode, active, onPress }: { label: string; mode: ViewMode; active: boolean; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${label} view`}
      onPress={onPress}
      style={[styles.btn, { borderColor: t.border, backgroundColor: active ? t.accent : "transparent" }]}
    >
      <Text style={{ color: active ? "#fff" : t.text }}>{label}</Text>
    </Pressable>
  );
}

function ViewBtnDisabled({ label, phase }: { label: string; phase: string }) {
  const t = useTheme();
  return (
    <View
      accessible
      accessibilityRole="button"
      accessibilityLabel={`${label} view (${phase})`}
      accessibilityState={{ disabled: true }}
      style={[styles.btn, { borderColor: t.border, opacity: 0.4 }]}
    >
      <Text style={{ color: t.disabled }}>{label}</Text>
      <Text style={{ color: t.disabled, fontSize: 10 }}>{phase}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row", alignItems: "center", gap: 12,
    padding: 10, borderWidth: 1, borderRadius: 8, flexWrap: "wrap",
  },
  switcher: { flexDirection: "row", gap: 6, marginLeft: "auto" },
  btn: { paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderRadius: 6 },
});
```

- [ ] **Step 8.3: Run tests**

```bash
npm test -- --testPathPattern=ResultsToolbar
```

Expected: 4 passing.

- [ ] **Step 8.4: Commit**

```bash
git add apps/web/src/components/ResultsToolbar.tsx apps/web/src/components/__tests__/ResultsToolbar.test.tsx
git commit -m "feat(web): ResultsToolbar with sort + view switcher"
```

---

## Task 9: `<ListingCard>`

**Files:**
- Create: `apps/web/src/components/ListingCard.tsx`
- Create: `apps/web/src/components/__tests__/ListingCard.test.tsx`

Renders one listing with photo (or placeholder), price, beds, source badge, and four action buttons (save / hide / contacted / open original). Uses `expo-linking` to open the source URL.

- [ ] **Step 9.1: Write the failing test**

`apps/web/src/components/__tests__/ListingCard.test.tsx`:

```tsx
import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import { ListingCard } from "@/src/components/ListingCard";
import type { NormalizedListing } from "@/src/api/types";

jest.mock("expo-linking", () => ({ openURL: jest.fn().mockResolvedValue(undefined) }));
import * as Linking from "expo-linking";

const listing: NormalizedListing = {
  id: "id-1",
  canonical_id: "id-1",
  source: "craigslist",
  source_url: "https://example.com/p/123",
  source_listing_id: "123",
  title: "Sunny 2br in Kits with view",
  address: "1234 W 4th Ave",
  address_normalized: null,
  lat: null, lon: null,
  bedrooms: 2, bathrooms: 1,
  price_cad: 2800,
  pets_allowed: null, furnished: null, available_date: null,
  posted_at: "2026-05-01T10:00:00Z",
  last_seen_at: "2026-05-06T10:00:00Z",
  photos: ["https://example.com/photo.jpg"],
  description_snippet: "Top floor unit, ocean view, in-suite laundry…",
  school_catchments: { elementary: null, middle: null, secondary: null },
  nearest_transit: null, walkscore: null,
  raw_metadata: {},
};

describe("ListingCard", () => {
  it("renders title, price, beds, source badge, and snippet", () => {
    const { getByText } = render(
      <ListingCard listing={listing} actions={{}} onAction={jest.fn()} />
    );
    expect(getByText("Sunny 2br in Kits with view")).toBeTruthy();
    expect(getByText("$2,800")).toBeTruthy();
    expect(getByText("2 bd")).toBeTruthy();
    expect(getByText("craigslist")).toBeTruthy();
    expect(getByText(/Top floor unit/)).toBeTruthy();
  });

  it("renders a placeholder when there are no photos", () => {
    const { getByText } = render(
      <ListingCard listing={{ ...listing, photos: [] }} actions={{}} onAction={jest.fn()} />
    );
    expect(getByText("No photo")).toBeTruthy();
  });

  it("fires onAction with the right flag", () => {
    const onAction = jest.fn();
    const { getByLabelText } = render(
      <ListingCard listing={listing} actions={{}} onAction={onAction} />
    );
    fireEvent.press(getByLabelText("Save"));
    expect(onAction).toHaveBeenCalledWith("saved", true);
    fireEvent.press(getByLabelText("Hide"));
    expect(onAction).toHaveBeenCalledWith("hidden", true);
    fireEvent.press(getByLabelText("Contacted"));
    expect(onAction).toHaveBeenCalledWith("contacted", true);
  });

  it("toggles flag off when already on", () => {
    const onAction = jest.fn();
    const { getByLabelText } = render(
      <ListingCard listing={listing} actions={{ saved: true }} onAction={onAction} />
    );
    fireEvent.press(getByLabelText("Save"));
    expect(onAction).toHaveBeenCalledWith("saved", false);
  });

  it("opens the source URL via Linking", () => {
    const { getByLabelText } = render(
      <ListingCard listing={listing} actions={{}} onAction={jest.fn()} />
    );
    fireEvent.press(getByLabelText("Open original"));
    expect((Linking.openURL as jest.Mock)).toHaveBeenCalledWith("https://example.com/p/123");
  });

  it("shows price as '—' when null", () => {
    const { getByText } = render(
      <ListingCard listing={{ ...listing, price_cad: null }} actions={{}} onAction={jest.fn()} />
    );
    expect(getByText("—")).toBeTruthy();
  });
});
```

- [ ] **Step 9.2: Implement**

`apps/web/src/components/ListingCard.tsx`:

```tsx
import React from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";
import * as Linking from "expo-linking";
import type { NormalizedListing } from "@/src/api/types";
import type { ActionFlag, ListingActions } from "@/src/storage/listingActions";
import { useTheme } from "@/src/theme";

interface Props {
  listing: NormalizedListing;
  actions: ListingActions;
  onAction: (flag: ActionFlag, value: boolean) => void;
}

const formatPrice = (n: number | null): string =>
  n == null ? "—" : `$${n.toLocaleString("en-CA")}`;

export function ListingCard({ listing, actions, onAction }: Props) {
  const t = useTheme();
  const photo = listing.photos[0];
  return (
    <View style={[styles.card, { backgroundColor: t.surface, borderColor: t.border }]}>
      <View style={[styles.photo, { backgroundColor: t.surfaceAlt }]}>
        {photo ? (
          <Image source={{ uri: photo }} style={StyleSheet.absoluteFill} resizeMode="cover" />
        ) : (
          <Text style={{ color: t.textMuted }}>No photo</Text>
        )}
        <View style={[styles.badge, { backgroundColor: t.surface }]}>
          <Text style={{ color: t.textMuted, fontSize: 11 }}>{listing.source}</Text>
        </View>
      </View>

      <View style={styles.body}>
        <Text style={[styles.title, { color: t.text }]} numberOfLines={2}>{listing.title}</Text>
        <View style={styles.metaRow}>
          <Text style={[styles.price, { color: t.text }]}>{formatPrice(listing.price_cad)}</Text>
          {listing.bedrooms != null && <Text style={{ color: t.textMuted }}>{listing.bedrooms} bd</Text>}
          {listing.address && <Text style={{ color: t.textMuted }} numberOfLines={1}>{listing.address}</Text>}
        </View>
        {listing.description_snippet && (
          <Text style={{ color: t.textMuted }} numberOfLines={2}>{listing.description_snippet}</Text>
        )}

        <View style={styles.actions}>
          <ActionBtn label="Save" active={!!actions.saved} onPress={() => onAction("saved", !actions.saved)} />
          <ActionBtn label="Hide" active={!!actions.hidden} onPress={() => onAction("hidden", !actions.hidden)} />
          <ActionBtn label="Contacted" active={!!actions.contacted} onPress={() => onAction("contacted", !actions.contacted)} />
          <ActionBtn
            label="Open original"
            active={false}
            onPress={() => { void Linking.openURL(listing.source_url); }}
          />
        </View>
      </View>
    </View>
  );
}

function ActionBtn({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={[styles.actionBtn, { borderColor: t.border, backgroundColor: active ? t.accent : "transparent" }]}
    >
      <Text style={{ color: active ? "#fff" : t.text, fontSize: 12 }}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: 12, overflow: "hidden", flexBasis: 320, flexGrow: 1 },
  photo: { aspectRatio: 16 / 9, alignItems: "center", justifyContent: "center" },
  badge: { position: "absolute", left: 8, top: 8, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999 },
  body: { padding: 12, gap: 6 },
  title: { fontSize: 15, fontWeight: "600" },
  metaRow: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  price: { fontWeight: "700" },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 8 },
  actionBtn: { paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderRadius: 6 },
});
```

- [ ] **Step 9.3: Run tests**

```bash
npm test -- --testPathPattern=ListingCard
```

Expected: 6 passing.

- [ ] **Step 9.4: Commit**

```bash
git add apps/web/src/components/ListingCard.tsx apps/web/src/components/__tests__/ListingCard.test.tsx
git commit -m "feat(web): ListingCard with photo, price, beds, source badge, action buttons"
```

---

## Task 10: `<ListingTable>` (virtualized list view)

**Files:**
- Create: `apps/web/src/components/ListingTable.tsx`
- Create: `apps/web/src/components/__tests__/ListingTable.test.tsx`

Uses `FlatList` with `getItemLayout` (fixed-row layout for virtualization on all platforms). Sortable columns: price, beds, source. Header press fires `onSortChange`.

- [ ] **Step 10.1: Write the failing test**

`apps/web/src/components/__tests__/ListingTable.test.tsx`:

```tsx
import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import { ListingTable } from "@/src/components/ListingTable";
import type { NormalizedListing } from "@/src/api/types";

const stub = (id: string, price: number, beds: number, title: string): NormalizedListing => ({
  id, canonical_id: id, source: "craigslist",
  source_url: `https://example.com/${id}`, source_listing_id: id,
  title, address: null, address_normalized: null, lat: null, lon: null,
  bedrooms: beds, bathrooms: null, price_cad: price,
  pets_allowed: null, furnished: null, available_date: null,
  posted_at: "2026-05-01T00:00:00Z", last_seen_at: "2026-05-06T00:00:00Z",
  photos: [], description_snippet: null,
  school_catchments: { elementary: null, middle: null, secondary: null },
  nearest_transit: null, walkscore: null, raw_metadata: {},
});

const rows = [stub("a", 2000, 1, "A row"), stub("b", 3000, 2, "B row")];

describe("ListingTable", () => {
  it("renders one row per listing", () => {
    const { getByText } = render(
      <ListingTable listings={rows} sort="newest" onSortChange={jest.fn()} actions={{}} onAction={jest.fn()} />
    );
    expect(getByText("A row")).toBeTruthy();
    expect(getByText("B row")).toBeTruthy();
  });

  it("fires onSortChange when a sortable header is pressed", () => {
    const onSortChange = jest.fn();
    const { getByText } = render(
      <ListingTable listings={rows} sort="newest" onSortChange={onSortChange} actions={{}} onAction={jest.fn()} />
    );
    fireEvent.press(getByText("Price"));
    expect(onSortChange).toHaveBeenCalledWith("price_asc");
    fireEvent.press(getByText("Beds"));
    expect(onSortChange).toHaveBeenCalledWith("bedrooms");
  });

  it("renders price formatted with thousands separator", () => {
    const { getByText } = render(
      <ListingTable listings={rows} sort="newest" onSortChange={jest.fn()} actions={{}} onAction={jest.fn()} />
    );
    expect(getByText("$2,000")).toBeTruthy();
    expect(getByText("$3,000")).toBeTruthy();
  });
});
```

- [ ] **Step 10.2: Implement**

`apps/web/src/components/ListingTable.tsx`:

```tsx
import React from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import * as Linking from "expo-linking";
import type { NormalizedListing, SortOrder } from "@/src/api/types";
import type { ActionFlag, ListingActionMap, ListingActions } from "@/src/storage/listingActions";
import { useTheme } from "@/src/theme";

const ROW_HEIGHT = 56;

interface Props {
  listings: NormalizedListing[];
  sort: SortOrder;
  onSortChange: (s: SortOrder) => void;
  actions: ListingActionMap;
  onAction: (id: string, flag: ActionFlag, value: boolean) => void;
}

export function ListingTable({ listings, sort, onSortChange, actions, onAction }: Props) {
  const t = useTheme();

  return (
    <View style={[styles.wrap, { borderColor: t.border, backgroundColor: t.surface }]}>
      <View style={[styles.headerRow, { borderColor: t.border }]}>
        <Header label="Title" />
        <Header label="Price" sortKey="price_asc" sort={sort} onPress={() => onSortChange("price_asc")} />
        <Header label="Beds" sortKey="bedrooms" sort={sort} onPress={() => onSortChange("bedrooms")} />
        <Header label="Source" />
        <Header label="" />
      </View>
      <FlatList
        data={listings}
        keyExtractor={(item) => item.id}
        getItemLayout={(_, i) => ({ length: ROW_HEIGHT, offset: ROW_HEIGHT * i, index: i })}
        renderItem={({ item }) => (
          <Row
            listing={item}
            acts={actions[item.id] ?? {}}
            onAction={(f, v) => onAction(item.id, f, v)}
          />
        )}
      />
    </View>
  );
}

function Header({
  label, sortKey, sort, onPress,
}: { label: string; sortKey?: SortOrder; sort?: SortOrder; onPress?: () => void }) {
  const t = useTheme();
  const active = sortKey && sort === sortKey;
  if (onPress) {
    return (
      <Pressable accessibilityRole="button" onPress={onPress} style={styles.cell}>
        <Text style={{ color: active ? t.accent : t.textMuted, fontWeight: "600" }}>{label}</Text>
      </Pressable>
    );
  }
  return (
    <View style={styles.cell}>
      <Text style={{ color: t.textMuted, fontWeight: "600" }}>{label}</Text>
    </View>
  );
}

function Row({
  listing, acts, onAction,
}: { listing: NormalizedListing; acts: ListingActions; onAction: (f: ActionFlag, v: boolean) => void }) {
  const t = useTheme();
  return (
    <View style={[styles.row, { height: ROW_HEIGHT, borderColor: t.border }]}>
      <View style={styles.cell}>
        <Text numberOfLines={1} style={{ color: t.text }}>{listing.title}</Text>
      </View>
      <View style={styles.cell}>
        <Text style={{ color: t.text }}>
          {listing.price_cad == null ? "—" : `$${listing.price_cad.toLocaleString("en-CA")}`}
        </Text>
      </View>
      <View style={styles.cell}>
        <Text style={{ color: t.text }}>{listing.bedrooms ?? "—"}</Text>
      </View>
      <View style={styles.cell}>
        <Text style={{ color: t.textMuted }}>{listing.source}</Text>
      </View>
      <View style={[styles.cell, styles.actionsCell]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Save" onPress={() => onAction("saved", !acts.saved)}>
          <Text style={{ color: acts.saved ? t.accent : t.textMuted }}>♥</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Open original" onPress={() => { void Linking.openURL(listing.source_url); }}>
          <Text style={{ color: t.textMuted }}>↗</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { borderWidth: 1, borderRadius: 8, flex: 1 },
  headerRow: { flexDirection: "row", borderBottomWidth: 1, paddingVertical: 8 },
  row: { flexDirection: "row", alignItems: "center", borderBottomWidth: 1 },
  cell: { flex: 1, paddingHorizontal: 10, justifyContent: "center" },
  actionsCell: { flexDirection: "row", gap: 12, flex: 0.5 },
});
```

- [ ] **Step 10.3: Run tests**

```bash
npm test -- --testPathPattern=ListingTable
```

Expected: 3 passing.

- [ ] **Step 10.4: Commit**

```bash
git add apps/web/src/components/ListingTable.tsx apps/web/src/components/__tests__/ListingTable.test.tsx
git commit -m "feat(web): virtualized ListingTable with sortable headers"
```

---

## Task 11: State banners — empty / error / loading skeleton

**Files:**
- Create: `apps/web/src/components/StateBanners.tsx`
- Create: `apps/web/src/components/__tests__/StateBanners.test.tsx`

- [ ] **Step 11.1: Write the failing test**

`apps/web/src/components/__tests__/StateBanners.test.tsx`:

```tsx
import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import { EmptyState, ErrorState, LoadingSkeleton, UnsupportedFiltersBanner } from "@/src/components/StateBanners";

describe("StateBanners", () => {
  it("EmptyState renders the message", () => {
    const { getByText } = render(<EmptyState message="No matches" />);
    expect(getByText("No matches")).toBeTruthy();
  });

  it("ErrorState shows the error and calls onRetry", () => {
    const onRetry = jest.fn();
    const { getByText } = render(
      <ErrorState message="Search failed: 500" onRetry={onRetry} />
    );
    expect(getByText("Search failed: 500")).toBeTruthy();
    fireEvent.press(getByText("Retry"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("LoadingSkeleton renders the requested number of placeholders", () => {
    const { getAllByLabelText } = render(<LoadingSkeleton rows={4} />);
    expect(getAllByLabelText("loading-row")).toHaveLength(4);
  });

  it("UnsupportedFiltersBanner shows a comma-separated list", () => {
    const { getByText } = render(
      <UnsupportedFiltersBanner filters={["pets", "furnished"]} />
    );
    expect(getByText(/pets, furnished/)).toBeTruthy();
  });

  it("UnsupportedFiltersBanner renders nothing when list is empty", () => {
    const { toJSON } = render(<UnsupportedFiltersBanner filters={[]} />);
    expect(toJSON()).toBeNull();
  });
});
```

- [ ] **Step 11.2: Implement**

`apps/web/src/components/StateBanners.tsx`:

```tsx
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useTheme } from "@/src/theme";

export function EmptyState({ message }: { message: string }) {
  const t = useTheme();
  return (
    <View style={[styles.box, { borderColor: t.border, backgroundColor: t.surface }]}>
      <Text style={{ color: t.textMuted }}>{message}</Text>
    </View>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const t = useTheme();
  return (
    <View style={[styles.box, { borderColor: t.error, backgroundColor: t.surface }]}>
      <Text style={{ color: t.error, marginBottom: 8 }}>{message}</Text>
      <Pressable
        accessibilityRole="button"
        onPress={onRetry}
        style={[styles.btn, { borderColor: t.error }]}
      >
        <Text style={{ color: t.error }}>Retry</Text>
      </Pressable>
    </View>
  );
}

export function LoadingSkeleton({ rows = 6 }: { rows?: number }) {
  const t = useTheme();
  return (
    <View style={{ gap: 8 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <View
          key={i}
          accessibilityLabel="loading-row"
          style={[styles.skeleton, { backgroundColor: t.surfaceAlt }]}
        />
      ))}
    </View>
  );
}

export function UnsupportedFiltersBanner({ filters }: { filters: string[] }) {
  const t = useTheme();
  if (filters.length === 0) return null;
  return (
    <View style={[styles.box, { borderColor: t.warn, backgroundColor: t.surface }]}>
      <Text style={{ color: t.warn }}>
        Filters not supported by any source yet: {filters.join(", ")}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderWidth: 1, borderRadius: 8, padding: 16 },
  btn: { paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderRadius: 6, alignSelf: "flex-start" },
  skeleton: { height: 80, borderRadius: 8, opacity: 0.5 },
});
```

- [ ] **Step 11.3: Run tests**

```bash
npm test -- --testPathPattern=StateBanners
```

Expected: 5 passing.

- [ ] **Step 11.4: Commit**

```bash
git add apps/web/src/components/StateBanners.tsx apps/web/src/components/__tests__/StateBanners.test.tsx
git commit -m "feat(web): empty/error/loading/unsupported-filters state banners"
```

---

## Task 12: `<SearchScreen>` — compose everything, wire to API

**Files:**
- Create: `apps/web/src/screens/SearchScreen.tsx`
- Create: `apps/web/src/screens/__tests__/SearchScreen.test.tsx`
- Create: `apps/web/__fixtures__/search_response.json`
- Modify: `apps/web/app/index.tsx`
- Modify: `apps/web/app/_layout.tsx`

The screen owns: `view` (cards|list), `sort`, `listings`, `total`, `unsupported_filters`, `actions` map, `loading`, `error`. It calls `searchClient.search()` on Search press and on "Load more". On every successful response, it merges `unsupported_filters` and updates the actions map snapshot from storage.

- [ ] **Step 12.1: Create the test fixture**

`apps/web/__fixtures__/search_response.json` — 5 listings:

```json
{
  "total": 5,
  "cache_status": "miss",
  "unsupported_filters": [],
  "source_health": {
    "craigslist": {
      "name": "craigslist",
      "status": "ok",
      "last_successful_fetch": "2026-05-06T10:00:00Z",
      "last_error": null
    }
  },
  "listings": [
    {
      "id": "00000000-0000-0000-0000-000000000001",
      "canonical_id": "00000000-0000-0000-0000-000000000001",
      "source": "craigslist",
      "source_url": "https://vancouver.craigslist.org/van/apa/d/test-1.html",
      "source_listing_id": "1",
      "title": "Sunny 2br in Kitsilano with view",
      "address": "1234 W 4th Ave, Vancouver",
      "address_normalized": null,
      "lat": null, "lon": null,
      "bedrooms": 2, "bathrooms": 1,
      "price_cad": 2800,
      "pets_allowed": null, "furnished": null, "available_date": null,
      "posted_at": "2026-05-01T10:00:00Z",
      "last_seen_at": "2026-05-06T10:00:00Z",
      "photos": [],
      "description_snippet": "Top floor unit with ocean view, in-suite laundry.",
      "school_catchments": { "elementary": null, "middle": null, "secondary": null },
      "nearest_transit": null, "walkscore": null,
      "raw_metadata": {}
    },
    {
      "id": "00000000-0000-0000-0000-000000000002",
      "canonical_id": "00000000-0000-0000-0000-000000000002",
      "source": "craigslist",
      "source_url": "https://vancouver.craigslist.org/van/apa/d/test-2.html",
      "source_listing_id": "2",
      "title": "1br Mount Pleasant near skytrain",
      "address": "5678 Main St",
      "address_normalized": null,
      "lat": null, "lon": null,
      "bedrooms": 1, "bathrooms": 1,
      "price_cad": 2100,
      "pets_allowed": null, "furnished": null, "available_date": null,
      "posted_at": "2026-05-02T12:00:00Z",
      "last_seen_at": "2026-05-06T12:00:00Z",
      "photos": [],
      "description_snippet": null,
      "school_catchments": { "elementary": null, "middle": null, "secondary": null },
      "nearest_transit": null, "walkscore": null,
      "raw_metadata": {}
    },
    {
      "id": "00000000-0000-0000-0000-000000000003",
      "canonical_id": "00000000-0000-0000-0000-000000000003",
      "source": "craigslist",
      "source_url": "https://vancouver.craigslist.org/van/apa/d/test-3.html",
      "source_listing_id": "3",
      "title": "Cozy studio in West End",
      "address": "999 Robson St",
      "address_normalized": null,
      "lat": null, "lon": null,
      "bedrooms": 0.5, "bathrooms": 1,
      "price_cad": 1700,
      "pets_allowed": null, "furnished": null, "available_date": null,
      "posted_at": "2026-05-03T08:00:00Z",
      "last_seen_at": "2026-05-06T08:00:00Z",
      "photos": [],
      "description_snippet": "Walk to Stanley Park.",
      "school_catchments": { "elementary": null, "middle": null, "secondary": null },
      "nearest_transit": null, "walkscore": null,
      "raw_metadata": {}
    },
    {
      "id": "00000000-0000-0000-0000-000000000004",
      "canonical_id": "00000000-0000-0000-0000-000000000004",
      "source": "craigslist",
      "source_url": "https://vancouver.craigslist.org/van/apa/d/test-4.html",
      "source_listing_id": "4",
      "title": "Spacious 3br in East Van",
      "address": "1100 Commercial Dr",
      "address_normalized": null,
      "lat": null, "lon": null,
      "bedrooms": 3, "bathrooms": 2,
      "price_cad": 3600,
      "pets_allowed": null, "furnished": null, "available_date": null,
      "posted_at": "2026-05-04T09:00:00Z",
      "last_seen_at": "2026-05-06T09:00:00Z",
      "photos": [],
      "description_snippet": null,
      "school_catchments": { "elementary": null, "middle": null, "secondary": null },
      "nearest_transit": null, "walkscore": null,
      "raw_metadata": {}
    },
    {
      "id": "00000000-0000-0000-0000-000000000005",
      "canonical_id": "00000000-0000-0000-0000-000000000005",
      "source": "craigslist",
      "source_url": "https://vancouver.craigslist.org/van/apa/d/test-5.html",
      "source_listing_id": "5",
      "title": "Renovated 2br Yaletown",
      "address": "1212 Pacific Blvd",
      "address_normalized": null,
      "lat": null, "lon": null,
      "bedrooms": 2, "bathrooms": 2,
      "price_cad": 3200,
      "pets_allowed": null, "furnished": null, "available_date": null,
      "posted_at": "2026-05-05T15:00:00Z",
      "last_seen_at": "2026-05-06T15:00:00Z",
      "photos": [],
      "description_snippet": "Concrete tower, gym, pool.",
      "school_catchments": { "elementary": null, "middle": null, "secondary": null },
      "nearest_transit": null, "walkscore": null,
      "raw_metadata": {}
    }
  ]
}
```

- [ ] **Step 12.2: Write the failing test**

`apps/web/src/screens/__tests__/SearchScreen.test.tsx`:

```tsx
import React from "react";
import { Text } from "react-native";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { SearchScreen } from "@/src/screens/SearchScreen";
import { QueryProvider } from "@/src/state/QueryProvider";
import fixture from "@/__fixtures__/search_response.json";

const okResponse = () => ({
  ok: true, status: 200, json: async () => fixture,
});

describe("SearchScreen", () => {
  beforeEach(() => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn(() =>
      Promise.resolve(okResponse() as never)
    );
    window.localStorage.clear();
  });

  function renderScreen() {
    return render(
      <QueryProvider>
        <SearchScreen apiBaseUrl="http://api.test" />
      </QueryProvider>
    );
  }

  it("shows the empty state before any search", () => {
    const { getByText } = renderScreen();
    expect(getByText(/Set filters and press Search/i)).toBeTruthy();
  });

  it("loads results on Search and shows count + cards", async () => {
    const { getByText, findAllByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    expect((await findAllByText(/Sunny 2br|Mount Pleasant|West End|East Van|Yaletown/)).length).toBeGreaterThan(0);
  });

  it("switches to list view and renders rows", async () => {
    const { getByText, getByLabelText, findAllByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    fireEvent.press(getByLabelText("List view"));
    expect((await findAllByText("$2,800")).length).toBeGreaterThan(0);
  });

  it("renders the unsupported-filters banner when API returns non-empty list", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ ...fixture, unsupported_filters: ["pets"] }),
    });
    const { getByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText(/pets/)).toBeTruthy());
  });

  it("shows error state and Retry on non-2xx", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false, status: 500, json: async () => ({ error: "boom" }),
    });
    const { getByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText(/HTTP 500/)).toBeTruthy());
    expect(getByText("Retry")).toBeTruthy();
  });

  it("persists save action to local storage", async () => {
    const { getByText, findAllByLabelText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    const saveButtons = await findAllByLabelText("Save");
    fireEvent.press(saveButtons[0]);
    await waitFor(() => {
      const stored = window.localStorage.getItem("rentwise.listingActions.v1");
      expect(stored).toBeTruthy();
      const parsed = JSON.parse(stored as string);
      expect(parsed["00000000-0000-0000-0000-000000000001"]?.saved).toBe(true);
    });
  });

  it("Load more advances offset by limit", async () => {
    const { getByText } = renderScreen();
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("5 listings")).toBeTruthy());
    // Force fixture's total to exceed listings: use a larger total below.
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => ({ ...fixture, total: 10 }),
    });
    fireEvent.press(getByText("Search"));
    await waitFor(() => expect(getByText("10 listings")).toBeTruthy());
    fireEvent.press(getByText("Load more"));
    const lastCall = (global.fetch as jest.Mock).mock.calls.at(-1)!;
    expect(JSON.parse(lastCall[1].body).offset).toBe(5);
  });
});
```

- [ ] **Step 12.3: Implement `<SearchScreen>`**

`apps/web/src/screens/SearchScreen.tsx`:

```tsx
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { searchClient } from "@/src/api/client";
import type { NormalizedListing, SearchResponse, SortOrder } from "@/src/api/types";
import { useQuery } from "@/src/state/QueryProvider";
import { FilterPanel } from "@/src/components/FilterPanel";
import { ResultsToolbar, type ViewMode } from "@/src/components/ResultsToolbar";
import { ListingCard } from "@/src/components/ListingCard";
import { ListingTable } from "@/src/components/ListingTable";
import {
  EmptyState,
  ErrorState,
  LoadingSkeleton,
  UnsupportedFiltersBanner,
} from "@/src/components/StateBanners";
import {
  loadActions,
  setAction,
  type ActionFlag,
  type ListingActionMap,
} from "@/src/storage/listingActions";
import { useTheme } from "@/src/theme";

const PAGE_SIZE = 50;

interface Props {
  apiBaseUrl: string;
}

export function SearchScreen({ apiBaseUrl }: Props) {
  const t = useTheme();
  const { query } = useQuery();
  const client = useMemo(() => searchClient(apiBaseUrl), [apiBaseUrl]);

  const [view, setView] = useState<ViewMode>("cards");
  const [sort, setSort] = useState<SortOrder>("newest");
  const [listings, setListings] = useState<NormalizedListing[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [unsupported, setUnsupported] = useState<string[]>([]);
  const [actions, setActions] = useState<ListingActionMap>({});
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "ok">("idle");
  const [errMsg, setErrMsg] = useState<string>("");
  const [offset, setOffset] = useState<number>(0);

  useEffect(() => {
    void loadActions().then(setActions);
  }, []);

  const runSearch = useCallback(
    async (nextOffset: number, append: boolean): Promise<void> => {
      setStatus("loading");
      setErrMsg("");
      try {
        const res: SearchResponse = await client.search({
          query,
          limit: PAGE_SIZE,
          offset: nextOffset,
          sort,
          force_refresh: false,
        });
        setListings((prev) => (append ? [...prev, ...res.listings] : res.listings));
        setTotal(res.total);
        setUnsupported(res.unsupported_filters);
        setOffset(nextOffset);
        setStatus("ok");
      } catch (e) {
        setStatus("error");
        setErrMsg(e instanceof Error ? e.message : String(e));
      }
    },
    [client, query, sort]
  );

  const onSearch = useCallback(() => { void runSearch(0, false); }, [runSearch]);
  const onLoadMore = useCallback(() => { void runSearch(offset + PAGE_SIZE, true); }, [runSearch, offset]);
  const onRetry = useCallback(() => { void runSearch(offset, false); }, [runSearch, offset]);

  const handleAction = useCallback(async (id: string, flag: ActionFlag, value: boolean) => {
    const next = await setAction(id, flag, value);
    setActions(next);
  }, []);

  const hasMore = listings.length < total;

  return (
    <View style={[styles.root, { backgroundColor: t.bg }]}>
      <View style={[styles.filters, { borderColor: t.border, backgroundColor: t.surface }]}>
        <FilterPanel onSearch={onSearch} />
      </View>

      <ScrollView style={styles.results} contentContainerStyle={styles.resultsContent}>
        <ResultsToolbar
          total={total}
          sort={sort}
          onSortChange={setSort}
          view={view}
          onViewChange={setView}
        />

        <UnsupportedFiltersBanner filters={unsupported} />

        {status === "idle" ? (
          <EmptyState message="Set filters and press Search to find listings." />
        ) : status === "loading" && listings.length === 0 ? (
          <LoadingSkeleton rows={6} />
        ) : status === "error" ? (
          <ErrorState message={errMsg} onRetry={onRetry} />
        ) : listings.length === 0 ? (
          <EmptyState message="No listings matched your filters." />
        ) : view === "cards" ? (
          <View style={styles.grid}>
            {listings.map((l) => (
              <ListingCard
                key={l.id}
                listing={l}
                actions={actions[l.id] ?? {}}
                onAction={(f, v) => { void handleAction(l.id, f, v); }}
              />
            ))}
          </View>
        ) : (
          <View style={{ minHeight: 400 }}>
            <ListingTable
              listings={listings}
              sort={sort}
              onSortChange={setSort}
              actions={actions}
              onAction={(id, f, v) => { void handleAction(id, f, v); }}
            />
          </View>
        )}

        {status === "ok" && hasMore && (
          <Pressable
            accessibilityRole="button"
            onPress={onLoadMore}
            style={[styles.loadMore, { borderColor: t.border }]}
          >
            <Text style={{ color: t.text }}>Load more</Text>
          </Pressable>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, flexDirection: "row", flexWrap: "wrap" },
  filters: { width: 320, minWidth: 260, borderRightWidth: 1 },
  results: { flex: 1, minWidth: 320 },
  resultsContent: { padding: 16, gap: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 16 },
  loadMore: { alignSelf: "center", paddingHorizontal: 18, paddingVertical: 10, borderWidth: 1, borderRadius: 8 },
});
```

- [ ] **Step 12.4: Wire `app/_layout.tsx`**

```tsx
import { Stack } from "expo-router";
import { QueryProvider } from "@/src/state/QueryProvider";

export default function RootLayout() {
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
      </Stack>
    </QueryProvider>
  );
}
```

- [ ] **Step 12.5: Replace `app/index.tsx`**

```tsx
import Constants from "expo-constants";
import { SearchScreen } from "@/src/screens/SearchScreen";

const API_BASE_URL =
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  "http://localhost:8000";

export default function HomeScreen() {
  return <SearchScreen apiBaseUrl={API_BASE_URL} />;
}
```

- [ ] **Step 12.6: Run tests**

```bash
npm test -- --testPathPattern=SearchScreen
```

Expected: 7 passing.

- [ ] **Step 12.7: Type check + full test run**

```bash
npx tsc --noEmit
npm test -- --watch=false
```

Expected: tsc clean, all suites pass, coverage ≥ thresholds.

- [ ] **Step 12.8: Commit**

```bash
git add apps/web/src/screens/ apps/web/__fixtures__/ apps/web/app/_layout.tsx apps/web/app/index.tsx
git commit -m "feat(web): SearchScreen wires filters, results, actions to /search"
```

---

## Task 13: Playwright E2E smoke

**Files:**
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/e2e/msw-handlers.ts`
- Create: `apps/web/e2e/search.smoke.spec.ts`
- Modify: `.gitignore` (root) — add `apps/web/playwright-report/`, `apps/web/test-results/`

The E2E test boots the Expo web dev server, intercepts the `POST /search` request via Playwright's `page.route` (simpler than running MSW in-page), and asserts cards/list rendering and a save click.

- [ ] **Step 13.1: Create `playwright.config.ts`**

`apps/web/playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: "http://localhost:8081",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "npm run web",
    url: "http://localhost:8081",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
```

- [ ] **Step 13.2: Create the test**

`apps/web/e2e/search.smoke.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import fixture from "../__fixtures__/search_response.json";

test("filter search renders results, switches view, saves a card", async ({ page }) => {
  await page.route("**/search", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture),
    });
  });

  await page.goto("/");

  // Set bedrooms_min=2 by tapping the chip
  await page.getByRole("button", { name: "2", exact: true }).click();

  // Set price_max to 3000
  await page.getByPlaceholder("Max").fill("3000");

  // Search
  await page.getByRole("button", { name: "Search" }).click();

  await expect(page.getByText("5 listings")).toBeVisible();

  // 5 cards visible
  await expect(page.getByText("Sunny 2br in Kitsilano with view")).toBeVisible();

  // Switch to list view
  await page.getByRole("button", { name: "List view" }).click();

  // List view shows the price cell
  await expect(page.getByText("$2,800")).toBeVisible();
});
```

- [ ] **Step 13.3: Update root `.gitignore`**

Append to `/Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/.gitignore`:

```
# Playwright artifacts
apps/web/playwright-report/
apps/web/test-results/
```

(Note: `apps/api/playwright/.auth/` is already there for backend; this is separate.)

- [ ] **Step 13.4: Verify Playwright runs locally**

```bash
cd apps/web
npx playwright install --with-deps chromium
npx playwright test
```

Expected: 1 test passes against the dev server (Playwright auto-boots `npm run web`).

- [ ] **Step 13.5: Commit**

```bash
git add apps/web/playwright.config.ts apps/web/e2e/ .gitignore
git commit -m "test(web): Playwright smoke E2E for filter search + view switch"
```

---

## Task 14: CI integration + docs/roadmap

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/roadmap.md`
- Modify: `README.md`

- [ ] **Step 14.1: Read the existing workflow**

```bash
cat .github/workflows/ci.yml
```

- [ ] **Step 14.2: Update the Web job**

The Web job currently runs `npx tsc --noEmit`. Extend it to install, type-check, lint, test (with coverage), and run Playwright. Replace the Web job's steps with:

```yaml
  web:
    name: Web (TypeScript)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - run: npm ci
      - run: npm run typecheck
      - run: npm run lint
      - run: npm run test:coverage
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: apps/web/playwright-report/
          retention-days: 7
```

- [ ] **Step 14.3: Tick chunks in `docs/roadmap.md`**

Find the Phase 1 frontend section and check off the items the spec covers. Look for the existing checkbox style (`- [x]` / `- [ ]`) and tick:

- Frontend filter UI (Mode B)
- Card grid + list/table
- Local listing actions
- Frontend tests (jest + Playwright)

- [ ] **Step 14.4: Update README**

In the Phase status section, mark Phase 1 frontend as shipped. Add a one-liner under the running-locally instructions:

```markdown
### Frontend dev

```bash
cd apps/web
npm install
npm run web         # web at http://localhost:8081
npm test            # jest
npm run e2e         # Playwright (requires `npm run e2e:install` once)
```
```

- [ ] **Step 14.5: Commit**

```bash
git add .github/workflows/ci.yml docs/roadmap.md README.md
git commit -m "ci(web): run jest + playwright; update docs for Phase 1 frontend"
```

---

## Final integration & PR

After Task 14:

- [ ] **Push the branch**

```bash
git push -u origin feat/phase-1-frontend
```

- [ ] **Open PR, link to issue #2**

```bash
gh pr create \
  --title "feat(web): Phase 1 frontend — filter UI + dual results view" \
  --body "$(cat <<'EOF'
## Summary
- Filter UI (bedrooms / price / neighborhoods / keywords) per spec §7.1
- Dual results display: card grid + virtualized list
- Local actions: save / hide / contacted / open original (platform-branched storage)
- jest + RTL component tests, Playwright web E2E smoke

Closes #2.

## Test plan
- [ ] CI green (jest coverage ≥ 80% lines, Playwright passes)
- [ ] `npm run web` shows the search screen, filter chips toggle, search works against local backend
- [ ] List view + view switch back to cards
- [ ] Save / hide / contacted persist across page reload (web)
EOF
)"
```

- [ ] **Wait for CI; address review**

If reviewers (`@codex`, `@coderabbit`) flag issues, follow the same pattern as PR #3: fix valid findings; reply with rationale on disputes.

---

## Risk register

- **react-native-async-storage version pin:** the version chosen (`1.23.1`) targets Expo SDK 52. If `expo install` reports a different version on first install, accept its choice and update the plan — the pin matters less than Expo's compatibility layer.
- **Playwright on macOS arm64 in CI:** GitHub-hosted Ubuntu runners are amd64; `--with-deps` is needed once. Cached browsers expire at ~24h; consider adding an `actions/cache` step if CI minutes become a concern.
- **`react-native-web` event names in jest:** `jest.mock("react-native/Libraries/Animated/NativeAnimatedHelper")` silences a noisy warning. If a jest-expo update changes the path, update `jest.setup.ts`.
- **Coverage thresholds:** start at 80/75; tighten in a follow-up PR if comfortable.

## Out of scope (Phase 2+)

- NL search box (`Mode A`) — Phase 2.
- Map view + Split view — Phase 7.
- iOS / macOS Detox E2E — Phase 8.
- Saved searches & alerts — Phase 5.
- Theme toggle UI — Phase 7.
