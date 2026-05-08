import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { searchClient } from "@/src/api/client";
import type {
  NormalizedListing,
  NormalizedQuery,
  SearchResponse,
  SortOrder,
} from "@/src/api/types";
import { useQuery } from "@/src/state/QueryProvider";
import { FilterPanel } from "@/src/components/FilterPanel";
import { ModeToggle } from "@/src/components/ModeToggle";
import { NLSearchBar } from "@/src/components/NLSearchBar";
import { ParsedQueryChips } from "@/src/components/ParsedQueryChips";
import { ResultsToolbar, type ViewMode } from "@/src/components/ResultsToolbar";
import { ListingCard } from "@/src/components/ListingCard";
import { ListingTable } from "@/src/components/ListingTable";
import { MapView } from "@/src/components/MapView";
import { SaveSearchForm } from "@/src/components/SaveSearchForm";
import { SavedSearchesDrawer } from "@/src/components/SavedSearchesDrawer";
import { groupByCanonical } from "@/src/lib/listingClusters";
import { defaultViewForWidth, isStacked, useViewportWidth } from "@/src/lib/responsive";
import {
  decodeQueryFromParams,
  encodeQueryToParams,
  hasAnyParams,
} from "@/src/lib/queryUrl";
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
  const { query, mode, replace } = useQuery();
  const client = useMemo(() => searchClient(apiBaseUrl), [apiBaseUrl]);

  // Phase 7 PR-C-1: viewport-aware initial view. Mount-only so a user
  // who picks Cards on a wide screen and resizes narrower keeps Cards.
  const viewportWidth = useViewportWidth();
  const initialView = useMemo<ViewMode>(
    () => defaultViewForWidth(viewportWidth),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  const [view, setView] = useState<ViewMode>(initialView);
  // True when filter sidebar should stack above results (narrow screens).
  // Re-evaluates on resize because layout *should* react live, unlike `view`.
  const stacked = isStacked(viewportWidth);
  // On narrow viewports the filter pane is collapsed by default to give the
  // results room to breathe. The user can expand it via the toolbar toggle.
  const [filtersOpen, setFiltersOpen] = useState<boolean>(!stacked);
  const [sort, setSort] = useState<SortOrder>("newest");
  const [listings, setListings] = useState<NormalizedListing[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [unsupported, setUnsupported] = useState<string[]>([]);
  const [actions, setActions] = useState<ListingActionMap>({});
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "ok">("idle");
  const [errMsg, setErrMsg] = useState<string>("");
  const [savedDrawerOpen, setSavedDrawerOpen] = useState(false);
  const [savePromptOpen, setSavePromptOpen] = useState(false);
  // Phase 7 PR-B: selection sync between map + list. Hover lives in
  // its own state so the highlight is responsive without forcing the
  // parent to re-render the whole grid; click commits to selection.
  const [selectedListingId, setSelectedListingId] = useState<string | null>(null);
  const [overlays, setOverlays] = useState<{ catchments: boolean; skytrain: boolean }>({
    catchments: false,
    skytrain: false,
  });
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

  // Phase 7 PR-C-2: hydrate query state from URL params on first mount and
  // auto-fire one search if there were any. Mount-only — subsequent URL
  // changes come from our own onSearch path and shouldn't loop here.
  const mountParams = useLocalSearchParams<Record<string, string | string[]>>();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const decoded = decodeQueryFromParams(mountParams);
    if (hasAnyParams(decoded)) {
      replace(decoded);
      void runSearch(0, false, decoded);
    }
    // Mount-only: capture mountParams snapshot at first render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runSearch = useCallback(
    async (
      nextOffset: number,
      append: boolean,
      queryOverride?: NormalizedQuery,
    ): Promise<void> => {
      const myId = ++reqIdRef.current;
      hasSearchedRef.current = true;
      setLastCall({ offset: nextOffset, append });
      setStatus("loading");
      setErrMsg("");
      try {
        const res: SearchResponse = await client.search({
          // queryOverride is for the mount-from-URL path: replace() schedules
          // a state update but the closure here still captures the stale
          // empty query, so the caller passes the decoded query explicitly.
          query: queryOverride ?? query,
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

  // Phase 7 PR-C-2: when the user kicks off a search, sync the current
  // query into the URL so the page is shareable / bookmarkable. Use
  // router.replace (vs setParams) so removed filters drop out of the URL
  // instead of merging with the prior set.
  const onSearch = useCallback(() => {
    const encoded = encodeQueryToParams(query);
    router.replace({
      pathname: "/",
      // expo-router params is Record<string, string>. Object.fromEntries on a
      // URLSearchParams gives exactly that.
      params: Object.fromEntries(encoded),
    });
    void runSearch(0, false);
  }, [query, runSearch]);
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
  // Phase 4 PR-D: collapse cross-source duplicates into one card per
  // canonical_id. Sort + pagination still operate on the flat list at
  // the API layer; clustering is purely a presentation step.
  const clusters = useMemo(() => groupByCanonical(listings), [listings]);

  return (
    <View style={[styles.root, stacked && styles.rootStacked, { backgroundColor: t.bg }]}>
      <View
        style={[
          styles.filters,
          stacked && styles.filtersStacked,
          { borderColor: t.border, backgroundColor: t.surface },
        ]}
      >
        {stacked ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={filtersOpen ? "Hide filters" : "Show filters"}
            accessibilityState={{ expanded: filtersOpen }}
            onPress={() => setFiltersOpen((open) => !open)}
            style={[styles.filtersToggle, { borderColor: t.border }]}
          >
            <Text style={{ color: t.text, fontWeight: "600" }}>
              {filtersOpen ? "Hide filters ▴" : "Show filters ▾"}
            </Text>
          </Pressable>
        ) : null}
        {!stacked || filtersOpen ? (
          <>
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
          </>
        ) : null}
      </View>

      <ScrollView style={styles.results} contentContainerStyle={styles.resultsContent}>
        <ResultsToolbar
          total={total}
          sort={sort}
          onSortChange={setSort}
          view={view}
          onViewChange={setView}
          onOpenSaved={() => setSavedDrawerOpen(true)}
          onSave={() => setSavePromptOpen(true)}
          canSave={status === "ok" && total > 0}
        />

        {savePromptOpen && (
          <SaveSearchForm
            client={client}
            query={query}
            onSaved={() => setSavePromptOpen(false)}
            onCancel={() => setSavePromptOpen(false)}
          />
        )}

        <SavedSearchesDrawer
          visible={savedDrawerOpen}
          onClose={() => setSavedDrawerOpen(false)}
          client={client}
          onLoad={(q) => replace(q)}
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
            {clusters.map(({ primary, alternates }) => (
              <ListingCard
                key={primary.id}
                listing={primary}
                alternates={alternates}
                actions={actions[primary.id] ?? {}}
                onAction={(f, v) => { void handleAction(primary.id, f, v); }}
              />
            ))}
          </View>
        ) : view === "map" ? (
          <View style={{ minHeight: 480 }}>
            <MapView
              listings={listings}
              selectedListingId={selectedListingId}
              onSelectListing={setSelectedListingId}
              onHoverListing={setSelectedListingId}
              overlays={overlays}
              onToggleOverlay={(k) =>
                setOverlays((o) => ({ ...o, [k]: !o[k] }))
              }
              apiBaseUrl={apiBaseUrl}
              onSearchBbox={() => {
                // PR-C will encode bbox in URL params + add a backend filter.
                onSearch();
              }}
            />
          </View>
        ) : view === "split" ? (
          <View style={styles.split}>
            <View style={styles.splitMap}>
              <MapView
                listings={listings}
                selectedListingId={selectedListingId}
                onSelectListing={setSelectedListingId}
                onHoverListing={setSelectedListingId}
                overlays={overlays}
                onToggleOverlay={(k) =>
                  setOverlays((o) => ({ ...o, [k]: !o[k] }))
                }
                apiBaseUrl={apiBaseUrl}
                onSearchBbox={() => {
                  onSearch();
                }}
              />
            </View>
            <View style={styles.splitList}>
              <ListingTable
                listings={listings}
                sort={sort}
                onSortChange={setSort}
                actions={actions}
                onAction={(id, f, v) => { void handleAction(id, f, v); }}
                selectedListingId={selectedListingId}
                onSelectListing={setSelectedListingId}
                onHoverListing={setSelectedListingId}
              />
            </View>
          </View>
        ) : (
          <View style={{ minHeight: 400 }}>
            <ListingTable
              listings={listings}
              sort={sort}
              onSortChange={setSort}
              actions={actions}
              onAction={(id, f, v) => { void handleAction(id, f, v); }}
              selectedListingId={selectedListingId}
              onSelectListing={setSelectedListingId}
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
  // Narrow viewports: stack filters above results, full width.
  rootStacked: { flexDirection: "column", flexWrap: "nowrap" },
  // alignSelf:"stretch" → the column inherits the row's cross-axis
  // height so the inner ScrollView in FilterPanel has a bounded
  // height to scroll within. maxHeight ties it to the viewport on
  // web specifically (RN ignores the string units gracefully).
  filters: {
    width: 320,
    minWidth: 260,
    borderRightWidth: 1,
    alignSelf: "stretch",
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    maxHeight: ("100vh" as any),
  },
  filtersStacked: {
    width: "100%",
    minWidth: 0,
    borderRightWidth: 0,
    borderBottomWidth: 1,
    alignSelf: "auto",
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    maxHeight: ("none" as any),
  },
  filtersToggle: {
    paddingHorizontal: 12,
    paddingVertical: 14,
    borderBottomWidth: 1,
    alignItems: "flex-start",
  },
  modeRow: { padding: 12, borderBottomWidth: 1, borderColor: "transparent" },
  nlPane: { padding: 12, gap: 12 },
  searchBtn: { alignSelf: "flex-end", paddingHorizontal: 18, paddingVertical: 10, borderRadius: 8 },
  results: { flex: 1, minWidth: 320 },
  resultsContent: { padding: 16, gap: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 16 },
  loadMore: { alignSelf: "center", paddingHorizontal: 18, paddingVertical: 10, borderWidth: 1, borderRadius: 8 },
  split: { flexDirection: "row", flexWrap: "wrap", gap: 16, minHeight: 480 },
  splitMap: { flex: 1, minWidth: 320, minHeight: 480 },
  splitList: { flex: 1, minWidth: 320, minHeight: 480 },
});
