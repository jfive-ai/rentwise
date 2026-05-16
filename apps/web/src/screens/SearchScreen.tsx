import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
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
import { CompareDrawer } from "@/src/components/CompareDrawer";
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
import { addEntry as addNlHistoryEntry } from "@/src/storage/nlSearchHistory";
import {
  AdapterFailureBanner,
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
  const { query, mode, nlText, replace, lastParsedNlText, setLastParsedNlText } = useQuery();
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
  // Issue #119 — default to Best Match so the new ranking is the first
  // experience. Users can still pick Newest / Price etc. from the menu.
  const [sort, setSort] = useState<SortOrder>("match_desc");
  const [listings, setListings] = useState<NormalizedListing[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [unsupported, setUnsupported] = useState<string[]>([]);
  const [sourceHealth, setSourceHealth] = useState<
    SearchResponse["source_health"]
  >({});
  const [actions, setActions] = useState<ListingActionMap>({});
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "ok">("idle");
  const [errMsg, setErrMsg] = useState<string>("");
  const [savedDrawerOpen, setSavedDrawerOpen] = useState(false);
  const [savePromptOpen, setSavePromptOpen] = useState(false);
  // Phase 7 PR-B: selection sync between map + list. Hover lives in
  // its own state so the highlight is responsive without forcing the
  // parent to re-render the whole grid; click commits to selection.
  const [selectedListingId, setSelectedListingId] = useState<string | null>(null);
  // Issue #121 — compare-set: 2-4 listings ticked via per-card checkbox.
  const [compareIds, setCompareIds] = useState<Set<string>>(() => new Set());
  const [compareOpen, setCompareOpen] = useState(false);
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
  // Active in-flight stream's AbortController. A new search aborts the
  // previous one so the backend can cancel its adapter tasks instead
  // of finishing them in the background and wasting work (issue #113).
  const streamAbortRef = useRef<AbortController | null>(null);
  // Same idea for the auto-parse path (#101 → #102 review): if the user
  // edits NL text and re-clicks Search before the in-flight translate
  // resolves, the slower response must NOT replace() the now-stale
  // query, write lastParsedNlText, or kick off a runSearch — that
  // would overwrite the newer search's URL/state with the older intent.
  const parseReqIdRef = useRef(0);
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
      // Invalidate any in-flight NL parse: a runSearch call (from the
      // sort effect, URL hydration, filter-mode Search, etc.) means a
      // newer intent is committing fresh state, and a stale parse
      // resolving later must NOT replace() / runSearch over it
      // (#102 review). The parse-path's own runSearch call also bumps
      // here, but its commit happens BEFORE the runSearch — so it's
      // self-consistent.
      parseReqIdRef.current++;
      hasSearchedRef.current = true;
      setLastCall({ offset: nextOffset, append });
      setStatus("loading");
      setErrMsg("");
      const reqQuery = queryOverride ?? query;

      // Initial / fresh searches use the streaming endpoint so the user
      // sees listings as they arrive (issue #113). "Load more" stays on
      // legacy POST /search because the streaming endpoint has no
      // offset/limit semantics yet — it ships the full result set.
      const useStream = !append && nextOffset === 0;

      if (useStream) {
        // Cancel any prior in-flight stream so the backend stops its
        // adapter tasks rather than racing this one to completion.
        streamAbortRef.current?.abort();
        const ac = new AbortController();
        streamAbortRef.current = ac;

        // Reset the visible list so streamed listings replace, not append.
        setListings([]);
        setTotal(0);
        setUnsupported([]);
        setSourceHealth({});
        setOffset(0);
        // Codex P2 on PR #129: prune compare-set when starting a new search.
        // Stale IDs from the previous result set would otherwise still count
        // toward the toolbar threshold and the modal would open on a shorter
        // filtered list.
        setCompareIds(new Set());

        try {
          for await (const ev of client.searchStream(
            {
              query: reqQuery,
              limit: PAGE_SIZE,
              offset: 0,
              sort,
              force_refresh: false,
            },
            { signal: ac.signal },
          )) {
            if (myId !== reqIdRef.current) return; // superseded
            if (ev.event === "listing") {
              setListings((prev) => [...prev, ev.data]);
              setTotal((t) => t + 1);
            } else if (ev.event === "quality_flags") {
              // Issue #120 — finalizer with cross-listing flags.
              const flagMap = ev.flags;
              setListings((prev) =>
                prev.map((l) =>
                  flagMap[l.id] ? { ...l, quality_flags: flagMap[l.id] } : l,
                ),
              );
            } else if (ev.event === "complete") {
              setTotal(ev.total);
              setUnsupported(ev.unsupported_filters);
              setSourceHealth(ev.source_health);
              setStatus("ok");
            }
          }
        } catch (e) {
          if (myId !== reqIdRef.current) return; // superseded
          // AbortError means we cancelled this stream because a newer
          // search took over — that's not user-visible failure.
          if (e instanceof DOMException && e.name === "AbortError") return;
          setStatus("error");
          setErrMsg(e instanceof Error ? e.message : String(e));
        }
        return;
      }

      try {
        const res: SearchResponse = await client.search({
          // queryOverride is for the mount-from-URL path: replace() schedules
          // a state update but the closure here still captures the stale
          // empty query, so the caller passes the decoded query explicitly.
          query: reqQuery,
          limit: PAGE_SIZE,
          offset: nextOffset,
          sort,
          force_refresh: false,
        });
        if (myId !== reqIdRef.current) return; // superseded by a newer call
        setListings((prev) => (append ? [...prev, ...res.listings] : res.listings));
        setTotal(res.total);
        setUnsupported(res.unsupported_filters);
        setSourceHealth(res.source_health);
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

  // Sync the current query into the URL so the page is shareable /
  // bookmarkable, then fire the search. We bypass `router.replace` and use
  // raw `history.replaceState` because expo-router's `replace` was
  // unmounting+remounting SearchScreen mid-search — the in-flight setState
  // calls then committed to a torn-down instance and the user saw a frozen
  // "Set filters and press Search" empty state even though POST /search had
  // returned 200. `history.replaceState` updates the URL without touching
  // the routing tree, so the state setters stay live. Existing
  // useLocalSearchParams() readers still see the new query string on next
  // mount (e.g. shared link).
  const onSearch = useCallback(() => {
    // Record the NL draft to history on Search too, not just on Parse —
    // many users will type and hit Search without ever pressing Parse,
    // and the original "remember last query" ask covers that flow.
    if (mode === "nl" && nlText.trim().length > 0) {
      void addNlHistoryEntry(nlText);
    }

    // #101: in NL mode, if the current text hasn't been parsed yet (or
    // has changed since the last parse), translate it before searching.
    // The bottom Search button used to skip parsing entirely and ship
    // an empty structured query, so a "2 bedroom in Dunbar" search
    // returned everything Craigslist had.
    const trimmed = nlText.trim();
    if (mode === "nl" && trimmed.length > 0 && trimmed !== lastParsedNlText) {
      const myParseId = ++parseReqIdRef.current;
      setStatus("loading");
      setErrMsg("");
      void (async () => {
        try {
          const result = await client.translateQuery({ text: trimmed });
          // Race guard (#102 review): a newer Search click may have
          // bumped parseReqIdRef while we were awaiting. Drop the
          // stale response on the floor — don't replace the query,
          // don't write lastParsedNlText, don't fire runSearch.
          if (myParseId !== parseReqIdRef.current) return;
          replace(result.query);
          setLastParsedNlText(trimmed);
          // Sync URL with the freshly-parsed structured query (the
          // pre-#101 path used `query` from closure, which was still
          // empty at this point — push the parsed one).
          const qs = encodeQueryToParams(result.query).toString();
          if (typeof window !== "undefined") {
            const path = window.location.pathname;
            const next = qs ? `${path}?${qs}` : path;
            window.history.replaceState(null, "", next);
          }
          await runSearch(0, false, result.query);
        } catch (e) {
          if (myParseId !== parseReqIdRef.current) return;
          setStatus("error");
          setErrMsg(
            `Couldn't parse query — ${e instanceof Error ? e.message : String(e)}`,
          );
        }
      })();
      return;
    }

    const qs = encodeQueryToParams(query).toString();
    if (typeof window !== "undefined") {
      const path = window.location.pathname;
      const next = qs ? `${path}?${qs}` : path;
      window.history.replaceState(null, "", next);
    }
    void runSearch(0, false);
  }, [
    query,
    runSearch,
    mode,
    nlText,
    lastParsedNlText,
    client,
    replace,
    setLastParsedNlText,
  ]);
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
          // In stacked mode the wrapper hugs its toggle when collapsed
          // and takes the full column when open so the pinned Search
          // button is visible.
          stacked && filtersOpen && styles.filtersStackedOpen,
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
                  accessibilityState={{ busy: status === "loading", disabled: status === "loading" }}
                  accessibilityLabel={status === "loading" ? "Searching…" : "Search"}
                  onPress={onSearch}
                  disabled={status === "loading"}
                  style={({ pressed }) => [
                    styles.searchBtn,
                    {
                      backgroundColor: status === "loading" ? t.textMuted : t.accent,
                      opacity: pressed && status !== "loading" ? 0.85 : 1,
                    },
                  ]}
                >
                  {status === "loading" ? (
                    <View style={styles.searchBtnInner}>
                      <ActivityIndicator size="small" color="#fff" />
                      <Text style={{ color: "#fff", fontWeight: "600" }}>Searching…</Text>
                    </View>
                  ) : (
                    <Text style={{ color: "#fff", fontWeight: "600" }}>Search</Text>
                  )}
                </Pressable>
              </View>
            ) : (
              <FilterPanel onSearch={onSearch} searching={status === "loading"} />
            )}
          </>
        ) : null}
      </View>

      <ScrollView
        style={[
          styles.results,
          // When filters are open on narrow viewports they take the full
          // column; hide results so the column doesn't try to share space
          // (which would either squish the filter pane or hide the Search
          // button below the viewport). Closing the filter restores
          // results without unmounting — display:none preserves scroll
          // position and any in-flight state.
          stacked && filtersOpen && styles.resultsHiddenStacked,
        ]}
        contentContainerStyle={styles.resultsContent}
      >
        <ResultsToolbar
          total={total}
          sort={sort}
          onSortChange={setSort}
          view={view}
          onViewChange={setView}
          onOpenSaved={() => setSavedDrawerOpen(true)}
          onSave={() => setSavePromptOpen(true)}
          canSave={status === "ok" && total > 0}
          compareCount={compareIds.size}
          onCompare={() => setCompareOpen(true)}
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
        <AdapterFailureBanner sourceHealth={sourceHealth} />

        {status === "idle" ? (
          <EmptyState message="Set filters and press Search to find listings." />
        ) : status === "loading" && listings.length === 0 ? (
          <LoadingSkeleton rows={6} />
        ) : status === "error" ? (
          <ErrorState message={errMsg} onRetry={onRetry} />
        ) : listings.length === 0 ? (
          // If every queried source failed, the empty result isn't really
          // "no matches" — it's "no data to match against". Use a clearer
          // copy so the user knows to retry / check the banner above.
          <EmptyState
            message={
              Object.values(sourceHealth).length > 0 &&
              Object.values(sourceHealth).every((h) => h.status !== "ok")
                ? "Couldn't reach any source. See the banner above for details."
                : "No listings matched your filters."
            }
          />
        ) : view === "cards" ? (
          <View style={styles.grid}>
            {clusters.map(({ primary, alternates }) => (
              <ListingCard
                key={primary.id}
                listing={primary}
                alternates={alternates}
                actions={actions[primary.id] ?? {}}
                onAction={(f, v) => { void handleAction(primary.id, f, v); }}
                compareChecked={compareIds.has(primary.id)}
                onCompareToggle={(checked) => {
                  setCompareIds((prev) => {
                    const next = new Set(prev);
                    if (checked) {
                      if (next.size >= 4) return prev; // max 4 listings to compare
                      next.add(primary.id);
                    } else {
                      next.delete(primary.id);
                    }
                    return next;
                  });
                }}
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
              selectedNeighborhoods={query.neighborhoods}
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
                selectedNeighborhoods={query.neighborhoods}
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
      <CompareDrawer
        visible={compareOpen}
        listings={listings.filter((l) => compareIds.has(l.id))}
        onClose={() => setCompareOpen(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  // No flex-wrap: with wrap, a child that's naturally taller than the row
  // (FilterPanel's full content) makes the row line grow to that
  // content height, breaking alignSelf:stretch and pushing both the
  // sidebar's Search button and the results' bottom past the
  // viewport (where body's overflow:hidden clips them). Layout is
  // already responsive via the stacked switch below.
  root: { flex: 1, flexDirection: "row" },
  // Narrow viewports: stack filters above results, full width.
  rootStacked: { flexDirection: "column" },
  filters: {
    width: 320,
    minWidth: 260,
    borderRightWidth: 1,
    alignSelf: "stretch",
    // overflow:hidden lets the wrapper actually take the row's bounded
    // height even when the inner FilterPanel's natural content is
    // taller — without it, min-content keeps the wrapper at content
    // height and overflow leaks out of the screen container.
    overflow: "hidden",
  },
  filtersStacked: {
    width: "100%",
    minWidth: 0,
    borderRightWidth: 0,
    borderBottomWidth: 1,
    alignSelf: "auto",
  },
  // Stacked + open: take the full column so the FilterPanel's
  // flex:1 ScrollView gets a definite parent height (and the pinned
  // Search row stays on screen). Results is hidden in this state via
  // resultsHiddenStacked so it doesn't fight for column space.
  filtersStackedOpen: {
    flex: 1,
    minHeight: 0,
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
  searchBtnInner: { flexDirection: "row", alignItems: "center", gap: 8 },
  // minHeight:0 lets the ScrollView shrink below its content so its own
  // overflow:auto kicks in — without it, react-native-web's default
  // min-height:auto keeps the ScrollView at content height and the
  // results column overflows the screen container instead of scrolling.
  results: { flex: 1, minWidth: 320, minHeight: 0 },
  resultsHiddenStacked: { display: "none" },
  resultsContent: { padding: 16, gap: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 16 },
  loadMore: { alignSelf: "center", paddingHorizontal: 18, paddingVertical: 10, borderWidth: 1, borderRadius: 8 },
  split: { flexDirection: "row", flexWrap: "wrap", gap: 16, minHeight: 480 },
  splitMap: { flex: 1, minWidth: 320, minHeight: 480 },
  splitList: { flex: 1, minWidth: 320, minHeight: 480 },
});
