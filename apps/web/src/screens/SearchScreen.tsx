import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { searchClient } from "@/src/api/client";
import type { NormalizedListing, SearchResponse, SortOrder } from "@/src/api/types";
import { useQuery } from "@/src/state/QueryProvider";
import { FilterPanel } from "@/src/components/FilterPanel";
import { ModeToggle } from "@/src/components/ModeToggle";
import { NLSearchBar } from "@/src/components/NLSearchBar";
import { ParsedQueryChips } from "@/src/components/ParsedQueryChips";
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
  const { query, mode } = useQuery();
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
  const [lastCall, setLastCall] = useState<{ offset: number; append: boolean }>({
    offset: 0,
    append: false,
  });

  // Generation counter: each runSearch claims an id and only commits state if
  // it's still the latest. Prevents stale responses from overwriting newer ones
  // when calls overlap (e.g. rapid Search clicks, Search during Load more).
  const reqIdRef = useRef(0);
  // True after the user has triggered at least one search. Gates the sort-effect
  // so changing sort doesn't fetch on initial mount.
  const hasSearchedRef = useRef(false);

  useEffect(() => {
    void loadActions().then(setActions);
  }, []);

  const runSearch = useCallback(
    async (nextOffset: number, append: boolean): Promise<void> => {
      const myId = ++reqIdRef.current;
      hasSearchedRef.current = true;
      setLastCall({ offset: nextOffset, append });
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
        if (myId !== reqIdRef.current) return; // superseded by a newer call
        setListings((prev) => (append ? [...prev, ...res.listings] : res.listings));
        setTotal(res.total);
        setUnsupported(res.unsupported_filters);
        setOffset(nextOffset);
        setStatus("ok");
      } catch (e) {
        if (myId !== reqIdRef.current) return; // superseded
        setStatus("error");
        setErrMsg(e instanceof Error ? e.message : String(e));
      }
    },
    [client, query, sort]
  );

  const onSearch = useCallback(() => { void runSearch(0, false); }, [runSearch]);
  const onLoadMore = useCallback(() => { void runSearch(offset + PAGE_SIZE, true); }, [runSearch, offset]);
  // Retry replays the exact (offset, append) of the failed call so a Load-more
  // failure doesn't drop earlier pages.
  const onRetry = useCallback(
    () => { void runSearch(lastCall.offset, lastCall.append); },
    [runSearch, lastCall]
  );

  // Sort is a server-side parameter — re-run the search whenever it changes,
  // but skip the initial mount (no implicit fetch before the user asks).
  useEffect(() => {
    if (!hasSearchedRef.current) return;
    void runSearch(0, false);
    // runSearch is intentionally omitted: it captures `sort`, so including it
    // would cause a second fire after the first state update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sort]);

  const handleAction = useCallback(async (id: string, flag: ActionFlag, value: boolean) => {
    const next = await setAction(id, flag, value);
    setActions(next);
  }, []);

  const hasMore = listings.length < total;

  return (
    <View style={[styles.root, { backgroundColor: t.bg }]}>
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
  modeRow: { padding: 12, borderBottomWidth: 1, borderColor: "transparent" },
  nlPane: { padding: 12, gap: 12 },
  searchBtn: { alignSelf: "flex-end", paddingHorizontal: 18, paddingVertical: 10, borderRadius: 8 },
  results: { flex: 1, minWidth: 320 },
  resultsContent: { padding: 16, gap: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 16 },
  loadMore: { alignSelf: "center", paddingHorizontal: 18, paddingVertical: 10, borderWidth: 1, borderRadius: 8 },
});
