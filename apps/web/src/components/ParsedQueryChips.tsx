import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useQuery } from "@/src/state/QueryProvider";
import { useTheme } from "@/src/theme";

interface Chip {
  key: string;
  label: string;
  clear: () => void;
}

export function ParsedQueryChips() {
  const t = useTheme();
  const { query, set } = useQuery();

  const chips: Chip[] = [];
  if (query.bedrooms_min != null) {
    chips.push({
      key: "beds_min",
      label: `${query.bedrooms_min}+ beds`,
      clear: () => set({ bedrooms_min: null }),
    });
  }
  if (query.bedrooms_max != null) {
    chips.push({
      key: "beds_max",
      label: `≤${query.bedrooms_max} beds`,
      clear: () => set({ bedrooms_max: null }),
    });
  }
  if (query.price_min != null) {
    chips.push({
      key: "price_min",
      label: `≥$${query.price_min}`,
      clear: () => set({ price_min: null }),
    });
  }
  if (query.price_max != null) {
    chips.push({
      key: "price_max",
      label: `≤$${query.price_max}`,
      clear: () => set({ price_max: null }),
    });
  }
  for (const n of query.neighborhoods) {
    chips.push({
      key: `nbhd_${n}`,
      label: n,
      clear: () =>
        set({ neighborhoods: query.neighborhoods.filter((x) => x !== n) }),
    });
  }
  if (query.school_catchment) {
    chips.push({
      key: "school",
      label: `${query.school_catchment} catchment`,
      clear: () => set({ school_catchment: null }),
    });
  }
  if (query.pets !== "any") {
    chips.push({
      key: "pets",
      label:
        query.pets === "required"
          ? "pets required"
          : query.pets === "no"
            ? "no pets"
            : "pets ok",
      clear: () => set({ pets: "any" }),
    });
  }
  if (query.furnished !== "any") {
    chips.push({
      key: "furn",
      label: query.furnished === "yes" ? "furnished" : "unfurnished",
      clear: () => set({ furnished: "any" }),
    });
  }
  if (query.available_after) {
    chips.push({
      key: "avail",
      label: `from ${query.available_after}`,
      clear: () => set({ available_after: null }),
    });
  }
  if (query.transit_max_walk_minutes != null) {
    chips.push({
      key: "walk",
      label: `≤${query.transit_max_walk_minutes} min walk`,
      clear: () => set({ transit_max_walk_minutes: null }),
    });
  }
  for (const kw of query.free_text_keywords) {
    chips.push({
      key: `kw_${kw}`,
      label: `"${kw}"`,
      clear: () =>
        set({
          free_text_keywords: query.free_text_keywords.filter((x) => x !== kw),
        }),
    });
  }

  if (chips.length === 0) {
    return (
      <View style={styles.emptyWrap}>
        <Text style={{ color: t.textMuted, fontSize: 13 }}>
          No filters parsed yet — type a search above and press Parse.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      {chips.map((c) => (
        <Pressable
          key={c.key}
          accessibilityRole="button"
          accessibilityLabel={`Remove ${c.label}`}
          onPress={c.clear}
          style={[
            styles.chip,
            { borderColor: t.border, backgroundColor: t.surface },
          ]}
        >
          <Text style={{ color: t.text }}>
            {c.label} <Text style={{ color: t.textMuted }}>×</Text>
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  emptyWrap: { paddingVertical: 8 },
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderWidth: 1,
    borderRadius: 999,
  },
});
