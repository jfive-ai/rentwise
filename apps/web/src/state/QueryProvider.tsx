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
