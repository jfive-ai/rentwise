import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { ApiError, searchClient } from "@/src/api/client";
import { useQuery } from "@/src/state/QueryProvider";
import {
  addEntry as addHistoryEntry,
  clearHistory as clearHistoryEntries,
  loadHistory,
  removeEntry as removeHistoryEntry,
  subscribe as subscribeHistory,
} from "@/src/storage/nlSearchHistory";
import { useTheme } from "@/src/theme";

interface Props {
  apiBaseUrl: string;
}

function extractErrorDetail(e: unknown): string {
  if (e instanceof ApiError) {
    // FastAPI shape: { detail: { error, message } } — show the message so
    // the user can see *why* (e.g. "OpenRouter 401: No cookie auth credentials").
    const payload = e.payload as
      | { detail?: { message?: string } | string }
      | undefined;
    if (payload && typeof payload.detail === "object" && payload.detail?.message) {
      return payload.detail.message;
    }
    if (typeof payload?.detail === "string") return payload.detail;
    return e.status === 0 ? e.message : `HTTP ${e.status}`;
  }
  return e instanceof Error ? e.message : String(e);
}

export function NLSearchBar({ apiBaseUrl }: Props) {
  const t = useTheme();
  const { nlText, setNlText, set, reset, setMode, setLastParsedNlText } = useQuery();
  const client = useMemo(() => searchClient(apiBaseUrl), [apiBaseUrl]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);

  // Restore the most recent NL query on mount, but only if the user hasn't
  // already started typing in this session. The provider lives above the
  // mode-toggle, so nlText may already be non-empty when we mount inside
  // the NL pane after a parse round-trip. We read nlText through a ref so
  // a fast typist who started before loadHistory resolves doesn't get their
  // input clobbered by the captured initial value.
  const restoredRef = useRef(false);
  const nlTextRef = useRef(nlText);
  useEffect(() => {
    nlTextRef.current = nlText;
  }, [nlText]);
  useEffect(() => {
    void loadHistory().then((list) => {
      setHistory(list);
      if (restoredRef.current) return;
      restoredRef.current = true;
      if (list[0] && !nlTextRef.current) setNlText(list[0]);
    });
    // Subscribe so writes from elsewhere (e.g. SearchScreen.onSearch
    // recording the NL draft on Search press) are reflected here without
    // requiring a remount.
    const unsubscribe = subscribeHistory((next) => setHistory(next));
    return unsubscribe;
    // Mount-only: restore is a one-shot. Subsequent updates flow through
    // the subscriber and through onParse / onRemoveHistory.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onParse = useCallback(async () => {
    const text = nlText.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    // Record before the LLM call: pressing Parse is the user's commit
    // ("remember this query"). Whether the LLM succeeds shouldn't decide
    // whether their typed query survives in history — failed parses are
    // often ones the user will tweak and retry, so they need to be
    // findable in the recent list.
    const next = await addHistoryEntry(text);
    setHistory(next);
    try {
      const result = await client.translateQuery({ text });
      // Replace structured query with the LLM's interpretation; chips reflect
      // only what the LLM parsed, not stale filters from a previous mode.
      reset();
      set(result.query);
      // Tell SearchScreen this exact text has already been translated, so
      // the bottom Search button doesn't redundantly re-call the LLM (#101).
      setLastParsedNlText(text);
    } catch (e) {
      setError(`LLM unavailable: ${extractErrorDetail(e)}`);
    } finally {
      setBusy(false);
    }
  }, [client, nlText, reset, set, setLastParsedNlText]);

  const onSwitchToFilters = useCallback(() => {
    setError(null);
    setMode("filters");
  }, [setMode]);

  const onPickHistory = useCallback(
    (text: string) => {
      setNlText(text);
    },
    [setNlText],
  );

  const onRemoveHistory = useCallback(async (text: string) => {
    const next = await removeHistoryEntry(text);
    setHistory(next);
  }, []);

  const onClearHistory = useCallback(async () => {
    await clearHistoryEntries();
    setHistory([]);
  }, []);

  // Only block on in-flight requests. The empty-text guard lives in onParse
  // (so a press with empty input is a silent no-op). Coupling `disabled` to
  // `nlText` length raced with React's batching in CI: a press dispatched
  // between fireEvent.changeText and the next reconcile saw `disabled=true`
  // and was silently dropped.
  const disabled = busy;

  return (
    <View
      style={[
        styles.wrap,
        { borderColor: t.border, backgroundColor: t.surface },
      ]}
    >
      <TextInput
        accessibilityLabel="Search input"
        placeholder="Try: 2 bedroom in Kitsilano under 3000 pet ok"
        placeholderTextColor={t.textMuted}
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
          disabled={disabled}
          style={[
            styles.parseBtn,
            { backgroundColor: busy ? t.textMuted : t.accent },
          ]}
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
      {error ? (
        <View style={styles.errorWrap}>
          <Text style={[styles.error, { color: "#c00" }]} accessibilityRole="alert">
            {error}
          </Text>
          <View style={styles.errorActions}>
            <Pressable
              accessibilityRole="button"
              onPress={onSwitchToFilters}
              style={[styles.linkBtn, { borderColor: t.border }]}
            >
              <Text style={{ color: t.text }}>Use filter mode</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {history.length > 0 ? (
        <View style={styles.historyWrap}>
          <View style={styles.historyHeader}>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded: historyOpen }}
              accessibilityLabel={
                historyOpen ? "Hide recent searches" : "Show recent searches"
              }
              onPress={() => setHistoryOpen((open) => !open)}
              style={styles.historyToggle}
            >
              <Text style={{ color: t.textMuted, fontWeight: "600" }}>
                {historyOpen ? "Recent searches ▴" : `Recent searches (${history.length}) ▾`}
              </Text>
            </Pressable>
            {historyOpen ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Clear all recent searches"
                onPress={() => void onClearHistory()}
                style={styles.historyClear}
              >
                <Text style={{ color: t.textMuted, fontSize: 12 }}>Clear all</Text>
              </Pressable>
            ) : null}
          </View>
          {historyOpen ? (
            <View style={styles.historyList}>
              {history.map((entry) => (
                <View
                  key={entry}
                  style={[styles.historyRow, { borderColor: t.border }]}
                >
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={`Use search: ${entry}`}
                    onPress={() => onPickHistory(entry)}
                    style={styles.historyText}
                  >
                    <Text style={{ color: t.text }} numberOfLines={2}>
                      {entry}
                    </Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={`Remove search: ${entry}`}
                    onPress={() => void onRemoveHistory(entry)}
                    style={styles.historyRemove}
                    hitSlop={8}
                  >
                    <Text style={{ color: t.textMuted, fontSize: 16 }}>×</Text>
                  </Pressable>
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 12, borderWidth: 1, borderRadius: 8, gap: 8 },
  input: {
    minHeight: 56,
    padding: 8,
    borderWidth: 1,
    borderRadius: 6,
    textAlignVertical: "top",
  },
  row: { flexDirection: "row", justifyContent: "flex-end" },
  btnInner: { flexDirection: "row", alignItems: "center", gap: 6 },
  parseBtn: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 6 },
  parseBtnText: { color: "#fff", fontWeight: "600" },
  errorWrap: { marginTop: 4, gap: 6 },
  error: { fontSize: 13 },
  errorActions: { flexDirection: "row", gap: 8 },
  linkBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
  },
  historyWrap: { marginTop: 4, gap: 6 },
  historyHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  historyToggle: { paddingVertical: 4 },
  historyClear: { paddingVertical: 4, paddingHorizontal: 6 },
  historyList: { gap: 4 },
  historyRow: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 6,
    gap: 6,
  },
  historyText: { flex: 1, paddingVertical: 2 },
  historyRemove: {
    width: 24,
    height: 24,
    alignItems: "center",
    justifyContent: "center",
  },
});
