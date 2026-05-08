/**
 * Phase 5 PR-A: drawer that lists the user's saved searches.
 *
 * Triggered from the ResultsToolbar's ★ Saved button. Shows each saved
 * search as a row with its label, query summary, and Load / Delete
 * actions. Loading hydrates the QueryProvider state so the user can
 * keep iterating from there.
 */

import React, { useCallback, useEffect, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import type { ApiClient } from "@/src/api/client";
import type { NormalizedQuery, SavedSearchResponse } from "@/src/api/types";
import { useTheme } from "@/src/theme";

interface Props {
  visible: boolean;
  onClose: () => void;
  client: ApiClient;
  onLoad: (query: NormalizedQuery) => void;
}

type State =
  | { kind: "loading" }
  | { kind: "loaded"; items: SavedSearchResponse[] }
  | { kind: "error"; message: string };

export function SavedSearchesDrawer({ visible, onClose, client, onLoad }: Props) {
  const t = useTheme();
  const [state, setState] = useState<State>({ kind: "loading" });

  const refresh = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const res = await client.listSavedSearches();
      setState({ kind: "loaded", items: res.items });
    } catch (e) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [client]);

  useEffect(() => {
    if (visible) void refresh();
  }, [visible, refresh]);

  const onDelete = useCallback(
    async (cacheKey: string) => {
      try {
        await client.deleteSavedSearch(cacheKey);
        await refresh();
      } catch (e) {
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : String(e),
        });
      }
    },
    [client, refresh],
  );

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.drawer, { backgroundColor: t.bg, borderColor: t.border }]}>
          <View style={styles.header}>
            <Text style={[styles.title, { color: t.text }]}>Saved searches</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Close saved searches"
              onPress={onClose}
            >
              <Text style={{ color: t.textMuted }}>Close</Text>
            </Pressable>
          </View>

          <ScrollView style={styles.list} contentContainerStyle={styles.listContent}>
            {state.kind === "loading" && (
              <Text style={{ color: t.textMuted }}>Loading…</Text>
            )}
            {state.kind === "error" && (
              <Text style={{ color: "#a30" }}>Couldn&apos;t load: {state.message}</Text>
            )}
            {state.kind === "loaded" && state.items.length === 0 && (
              <Text style={{ color: t.textMuted }}>
                No saved searches yet. Run a search and press &quot;Save&quot; to keep it.
              </Text>
            )}
            {state.kind === "loaded" &&
              state.items.map((item) => (
                <SavedRow
                  key={item.cache_key}
                  item={item}
                  onLoad={() => {
                    onLoad(item.query);
                    onClose();
                  }}
                  onDelete={() => void onDelete(item.cache_key)}
                />
              ))}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function SavedRow({
  item,
  onLoad,
  onDelete,
}: {
  item: SavedSearchResponse;
  onLoad: () => void;
  onDelete: () => void;
}) {
  const t = useTheme();
  const summary = summarizeQuery(item.query);
  return (
    <View style={[styles.row, { borderColor: t.border, backgroundColor: t.surface }]}>
      <View style={{ flex: 1 }}>
        <Text style={[styles.rowLabel, { color: t.text }]}>
          {item.label || "(unlabeled)"}
        </Text>
        <Text style={{ color: t.textMuted, fontSize: 12 }}>{summary}</Text>
        {item.alert_enabled && item.alert_email ? (
          <Text style={{ color: t.textMuted, fontSize: 12 }}>
            Alerts → {item.alert_email} every {item.cadence_minutes} min
          </Text>
        ) : null}
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Load ${item.label || "saved search"}`}
        onPress={onLoad}
        style={[styles.btn, { borderColor: t.border }]}
      >
        <Text style={{ color: t.text }}>Load</Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Delete ${item.label || "saved search"}`}
        onPress={onDelete}
        style={[styles.btn, { borderColor: t.border }]}
      >
        <Text style={{ color: "#a30" }}>Delete</Text>
      </Pressable>
    </View>
  );
}

function summarizeQuery(q: NormalizedQuery): string {
  const parts: string[] = [];
  if (q.bedrooms_min != null) parts.push(`${q.bedrooms_min}+ bd`);
  if (q.price_max != null) parts.push(`≤$${q.price_max}`);
  if (q.neighborhoods.length > 0) parts.push(q.neighborhoods.join(", "));
  if (q.school_catchment) parts.push(`catchment: ${q.school_catchment}`);
  if (q.transit_max_walk_minutes != null)
    parts.push(`≤${q.transit_max_walk_minutes} min walk`);
  return parts.join(" · ") || "(no filters)";
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: "flex-end",
    backgroundColor: "rgba(0,0,0,0.4)",
  },
  drawer: {
    maxHeight: "80%",
    borderTopWidth: 1,
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
    padding: 16,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  title: { fontSize: 16, fontWeight: "600" },
  list: { flex: 1 },
  listContent: { gap: 8 },
  row: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    padding: 12,
    borderWidth: 1,
    borderRadius: 8,
  },
  rowLabel: { fontWeight: "600" },
  btn: { paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderRadius: 6 },
});
