import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { SortOrder } from "@/src/api/types";
import { useTheme } from "@/src/theme";

export type ViewMode = "cards" | "list";

const SORT_LABEL: Record<SortOrder, string> = {
  newest: "Newest",
  price_asc: "Price ↑",
  price_desc: "Price ↓",
  bedrooms: "Bedrooms",
};
const SORT_CYCLE: SortOrder[] = ["newest", "price_asc", "price_desc", "bedrooms"];

function nextSort(s: SortOrder): SortOrder {
  const i = SORT_CYCLE.indexOf(s);
  return SORT_CYCLE[(i + 1) % SORT_CYCLE.length];
}

interface Props {
  total: number;
  sort: SortOrder;
  onSortChange: (s: SortOrder) => void;
  view: ViewMode;
  onViewChange: (v: ViewMode) => void;
}

export function ResultsToolbar({ total, sort, onSortChange, view, onViewChange }: Props) {
  const t = useTheme();
  return (
    <View style={[styles.row, { borderColor: t.border, backgroundColor: t.surface }]}>
      <Text style={{ color: t.text, fontWeight: "600" }}>{total} listings</Text>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Sort by"
        onPress={() => onSortChange(nextSort(sort))}
        style={[styles.btn, { borderColor: t.border }]}
      >
        <Text style={{ color: t.text }}>Sort: {SORT_LABEL[sort]} ▾</Text>
      </Pressable>

      <View style={styles.switcherWrap}>
        <View style={styles.switcher}>
          <ViewBtn label="Cards" active={view === "cards"} onPress={() => onViewChange("cards")} />
          <ViewBtn label="List" active={view === "list"} onPress={() => onViewChange("list")} />
          <ViewBtnDisabled label="Map" phase="Phase 7" />
          <ViewBtnDisabled label="Split" phase="Phase 7" />
        </View>
        <Text style={{ color: t.disabled, fontSize: 10, textAlign: "center" }}>Phase 7</Text>
      </View>
    </View>
  );
}

function ViewBtn({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${label} view`}
      onPress={onPress}
      style={[styles.btn, { borderColor: t.border, backgroundColor: active ? t.accent : "transparent" }]}
    >
      <Text style={{ color: active ? "#fff" : t.text }}>{label}</Text>
    </Pressable>
  );
}

function ViewBtnDisabled({ label, phase }: { label: string; phase: string }) {
  const t = useTheme();
  return (
    <View
      accessible
      accessibilityRole="button"
      accessibilityLabel={`${label} view (${phase})`}
      accessibilityState={{ disabled: true }}
      style={[styles.btn, { borderColor: t.border, opacity: 0.4 }]}
    >
      <Text style={{ color: t.disabled }}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row", alignItems: "center", gap: 12,
    padding: 10, borderWidth: 1, borderRadius: 8, flexWrap: "wrap",
  },
  switcherWrap: { marginLeft: "auto", alignItems: "center", gap: 4 },
  switcher: { flexDirection: "row", gap: 6 },
  btn: { paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderRadius: 6 },
});
