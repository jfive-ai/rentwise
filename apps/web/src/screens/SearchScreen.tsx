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
