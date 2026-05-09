import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { type NormalizedQuery, emptyQuery } from "@/src/api/types";

type Mode = "nl" | "filters";

interface QueryContextValue {
  query: NormalizedQuery;
  set: (patch: Partial<NormalizedQuery>) => void;
  /** Replace the entire query (Phase 5 PR-A: load saved search). */
  replace: (next: NormalizedQuery) => void;
  reset: () => void;
  toggleNeighborhood: (name: string) => void;
  toggleKeyword: (k: string) => void;
  // NL-specific:
  mode: Mode;
  setMode: (m: Mode) => void;
  nlText: string;
  setNlText: (s: string) => void;
  /** The exact `nlText` that was last sent to /translate-query and
   * accepted (whether by NLSearchBar's Parse button or by SearchScreen's
   * auto-parse on Search). SearchScreen compares the current `nlText`
   * against this to decide whether to re-parse before searching — issue
   * #101: the bottom Search button used to skip parsing entirely. */
  lastParsedNlText: string;
  setLastParsedNlText: (s: string) => void;
}

const QueryContext = createContext<QueryContextValue | null>(null);

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [query, setQuery] = useState<NormalizedQuery>(() => emptyQuery());
  const [mode, setModeRaw] = useState<Mode>("filters");
  const [nlText, setNlText] = useState<string>("");
  const [lastParsedNlText, setLastParsedNlText] = useState<string>("");

  const set = useCallback((patch: Partial<NormalizedQuery>) => {
    if (Object.keys(patch).length === 0) return;
    setQuery((prev) => ({ ...prev, ...patch }));
  }, []);

  const reset = useCallback(() => setQuery(emptyQuery()), []);

  const replace = useCallback((next: NormalizedQuery) => {
    // Defensively merge over emptyQuery so any field the server omitted
    // (e.g. an older saved-search row written before a field was added)
    // falls back to its safe default.
    setQuery({ ...emptyQuery(), ...next });
  }, []);

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

  const setMode = useCallback((next: Mode) => {
    setModeRaw(next);
  }, []);

  const value = useMemo<QueryContextValue>(
    () => ({
      query,
      set,
      replace,
      reset,
      toggleNeighborhood,
      toggleKeyword,
      mode,
      setMode,
      nlText,
      setNlText,
      lastParsedNlText,
      setLastParsedNlText,
    }),
    [
      query,
      set,
      replace,
      reset,
      toggleNeighborhood,
      toggleKeyword,
      mode,
      setMode,
      nlText,
      lastParsedNlText,
    ]
  );

  return <QueryContext.Provider value={value}>{children}</QueryContext.Provider>;
}

export function useQuery(): QueryContextValue {
  const ctx = useContext(QueryContext);
  if (!ctx) throw new Error("useQuery() must be called inside a <QueryProvider>.");
  return ctx;
}
