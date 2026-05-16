// Issue #124 — collapsible panel above the results showing area context
// (median rent, sources, transit, schools). Only renders when the
// backend returned a populated NeighborhoodInsights row.

import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { NeighborhoodInsights } from "@/src/api/types";
import { useTheme } from "@/src/theme";

interface Props {
  insights: NeighborhoodInsights | null;
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  return `$${n.toLocaleString("en-CA")}`;
}

export function NeighborhoodInsightsPanel({ insights }: Props) {
  const t = useTheme();
  const [open, setOpen] = useState(true);
  if (!insights) return null;

  const sources = Object.entries(insights.source_breakdown).sort(
    ([, a], [, b]) => b - a,
  );
  const byBR = Object.entries(insights.median_rent_by_bedrooms).sort(([a], [b]) =>
    a.localeCompare(b),
  );

  return (
    <View
      style={[
        styles.wrap,
        { borderColor: t.border, backgroundColor: t.surfaceAlt },
      ]}
      accessibilityLabel={`Insights for ${insights.area_name}`}
    >
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={open ? "Collapse insights" : "Expand insights"}
        onPress={() => setOpen((v) => !v)}
        style={styles.header}
      >
        <Text style={{ color: t.text, fontSize: 14, fontWeight: "700" }}>
          🏘 {insights.area_name} — {insights.listing_count} listing
          {insights.listing_count === 1 ? "" : "s"}
        </Text>
        <Text style={{ color: t.textMuted, fontSize: 13 }}>
          {open ? "▴" : "▾"}
        </Text>
      </Pressable>

      {open && (
        <View style={styles.body}>
          <View style={styles.section}>
            <Text style={[styles.h, { color: t.textMuted }]}>Median rent</Text>
            <Text style={{ color: t.text, fontSize: 15, fontWeight: "700" }}>
              {fmt(insights.median_rent_overall)}/mo
            </Text>
            {byBR.length > 0 && (
              <View style={styles.chipRow}>
                {byBR.map(([k, v]) => (
                  <View
                    key={k}
                    style={[styles.chip, { borderColor: t.border }]}
                  >
                    <Text style={{ color: t.text, fontSize: 11 }}>
                      {k}: {fmt(v)}
                    </Text>
                  </View>
                ))}
              </View>
            )}
          </View>

          {sources.length > 0 && (
            <View style={styles.section}>
              <Text style={[styles.h, { color: t.textMuted }]}>By source</Text>
              <View style={styles.chipRow}>
                {sources.map(([k, v]) => (
                  <View
                    key={k}
                    style={[styles.chip, { borderColor: t.border }]}
                  >
                    <Text style={{ color: t.text, fontSize: 11 }}>
                      {k}: {v}
                    </Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {insights.nearby_skytrain_stations.length > 0 && (
            <View style={styles.section}>
              <Text style={[styles.h, { color: t.textMuted }]}>Transit</Text>
              <Text style={{ color: t.text, fontSize: 12 }} numberOfLines={2}>
                🚉 {insights.nearby_skytrain_stations.join(", ")}
              </Text>
            </View>
          )}

          {insights.schools.length > 0 && (
            <View style={styles.section}>
              <Text style={[styles.h, { color: t.textMuted }]}>Schools</Text>
              <Text style={{ color: t.text, fontSize: 12 }} numberOfLines={3}>
                🎓 {insights.schools.join(", ")}
              </Text>
            </View>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderWidth: 1,
    borderRadius: 8,
    marginBottom: 12,
    padding: 12,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  body: { marginTop: 10, gap: 10 },
  section: { gap: 4 },
  h: { fontSize: 11, fontWeight: "600", textTransform: "uppercase" },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 2 },
  chip: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
    borderWidth: 1,
  },
});
