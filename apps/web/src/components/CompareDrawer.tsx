// Issue #121 — side-by-side comparison modal.
//
// Opens from the ResultsToolbar when the user has 2-4 listings selected
// via the per-card checkbox. Renders a fixed-axis table plus a footer
// with deterministic "best on X" picks. Pure frontend — no API call.

import React from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import type { NormalizedListing } from "@/src/api/types";
import { recommend } from "@/src/lib/compare";
import { useTheme } from "@/src/theme";

interface Props {
  visible: boolean;
  listings: NormalizedListing[];
  onClose: () => void;
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  return `$${n.toLocaleString("en-CA")}`;
}

export function CompareDrawer({ visible, listings, onClose }: Props) {
  const t = useTheme();
  const picks = recommend(listings);

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent
      onRequestClose={onClose}
    >
      <View style={[styles.backdrop, { backgroundColor: "rgba(0,0,0,0.45)" }]}>
        <View
          style={[
            styles.sheet,
            { backgroundColor: t.surface, borderColor: t.border },
          ]}
        >
          <View style={styles.header}>
            <Text style={{ color: t.text, fontSize: 18, fontWeight: "700" }}>
              Compare {listings.length} listing{listings.length === 1 ? "" : "s"}
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Close comparison"
              onPress={onClose}
            >
              <Text style={{ color: t.textMuted, fontSize: 18 }}>✕</Text>
            </Pressable>
          </View>

          <ScrollView
            style={{ flex: 1 }}
            horizontal={false}
            contentContainerStyle={{ paddingBottom: 24 }}
          >
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ minWidth: "100%" }}
            >
              <View style={styles.table}>
                <Row
                  label=""
                  cells={listings.map((l) => l.title)}
                  bold
                  themeColor={t.text}
                  border={t.border}
                />
                <Row
                  label="Price"
                  cells={listings.map((l) => fmt(l.price_cad))}
                  themeColor={t.text}
                  border={t.border}
                />
                <Row
                  label="Bedrooms"
                  cells={listings.map((l) => (l.bedrooms ?? "—").toString())}
                  themeColor={t.text}
                  border={t.border}
                />
                <Row
                  label="Source"
                  cells={listings.map((l) => l.source)}
                  themeColor={t.textMuted}
                  border={t.border}
                />
                <Row
                  label="Address"
                  cells={listings.map((l) => l.address ?? "—")}
                  themeColor={t.textMuted}
                  border={t.border}
                />
                <Row
                  label="Transit walk"
                  cells={listings.map((l) =>
                    l.nearest_transit
                      ? `${l.nearest_transit.walk_minutes} min`
                      : "—",
                  )}
                  themeColor={t.text}
                  border={t.border}
                />
                <Row
                  label="Match score"
                  cells={listings.map((l) =>
                    l.match_score != null ? l.match_score.toString() : "—",
                  )}
                  themeColor={t.text}
                  border={t.border}
                  bold
                />
                <Row
                  label="Flags"
                  cells={listings.map((l) =>
                    (l.quality_flags || []).length === 0
                      ? "—"
                      : `⚠ ${(l.quality_flags || []).length}`,
                  )}
                  themeColor={t.text}
                  border={t.border}
                />
              </View>
            </ScrollView>

            {picks.length > 0 && (
              <View style={[styles.recsBlock, { borderColor: t.border }]}>
                <Text
                  style={{
                    color: t.text,
                    fontSize: 14,
                    fontWeight: "700",
                    marginBottom: 8,
                  }}
                >
                  Recommendations
                </Text>
                {picks.map((p) => (
                  <Text
                    key={`${p.axis}-${p.listingId}`}
                    style={{ color: t.text, fontSize: 13, marginBottom: 4 }}
                  >
                    • {p.reason}
                  </Text>
                ))}
              </View>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function Row({
  label,
  cells,
  bold,
  themeColor,
  border,
}: {
  label: string;
  cells: string[];
  bold?: boolean;
  themeColor: string;
  border: string;
}) {
  return (
    <View style={[styles.row, { borderColor: border }]}>
      <View style={[styles.cell, styles.cellLabel]}>
        <Text style={{ color: themeColor, fontWeight: "600", fontSize: 12 }}>
          {label}
        </Text>
      </View>
      {cells.map((c, i) => (
        <View key={i} style={[styles.cell, styles.cellValue]}>
          <Text
            style={{
              color: themeColor,
              fontWeight: bold ? "700" : "400",
              fontSize: 13,
            }}
            numberOfLines={3}
          >
            {c}
          </Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  sheet: {
    width: "100%",
    maxWidth: 960,
    maxHeight: "90%",
    borderRadius: 12,
    borderWidth: 1,
    padding: 16,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  table: { minWidth: 700 },
  row: { flexDirection: "row", borderBottomWidth: 1, paddingVertical: 8 },
  cell: { paddingHorizontal: 10, justifyContent: "center" },
  cellLabel: { width: 130, alignItems: "flex-start" },
  cellValue: { flex: 1, minWidth: 160, alignItems: "flex-start" },
  recsBlock: { marginTop: 16, paddingTop: 12, borderTopWidth: 1 },
});
