import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { SortOrder } from "@/src/api/types";
import { useTheme } from "@/src/theme";

export type ViewMode = "cards" | "list" | "map" | "split";

// Each entry shows up in the sort menu; the legacy "bedrooms" alias is
// intentionally absent so users always pick a directional option.
const SORT_OPTIONS: { value: SortOrder; label: string }[] = [
  // Issue #119 — best-match-first.
  { value: "match_desc", label: "Best match" },
  { value: "newest", label: "Newest" },
  { value: "title_asc", label: "Title A→Z" },
  { value: "title_desc", label: "Title Z→A" },
  { value: "price_asc", label: "Price ↑" },
  { value: "price_desc", label: "Price ↓" },
  { value: "bedrooms_asc", label: "Beds ↑" },
  { value: "bedrooms_desc", label: "Beds ↓" },
  { value: "source_asc", label: "Source A→Z" },
  { value: "source_desc", label: "Source Z→A" },
];

const SORT_LABEL: Record<SortOrder, string> = {
  match_desc: "Best match",
  newest: "Newest",
  title_asc: "Title A→Z",
  title_desc: "Title Z→A",
  price_asc: "Price ↑",
  price_desc: "Price ↓",
  bedrooms_asc: "Beds ↑",
  bedrooms_desc: "Beds ↓",
  bedrooms: "Beds ↓",
  source_asc: "Source A→Z",
  source_desc: "Source Z→A",
};

interface Props {
  total: number;
  sort: SortOrder;
  onSortChange: (s: SortOrder) => void;
  view: ViewMode;
  onViewChange: (v: ViewMode) => void;
  /** Phase 5 PR-A: opens the saved-searches drawer. */
  onOpenSaved?: () => void;
  /** Phase 5 PR-A: opens the inline "Save this search" form. */
  onSave?: () => void;
  /** Hide Save when there are no results yet (no search row to save). */
  canSave?: boolean;
  /** Issue #121: number of listings currently ticked for comparison. */
  compareCount?: number;
  /** Issue #121: open the comparison modal. */
  onCompare?: () => void;
}

export function ResultsToolbar({
  total,
  sort,
  onSortChange,
  view,
  onViewChange,
  onOpenSaved,
  onSave,
  canSave = false,
  compareCount = 0,
  onCompare,
}: Props) {
  const t = useTheme();
  const [sortOpen, setSortOpen] = useState(false);
  return (
    <View style={[styles.row, { borderColor: t.border, backgroundColor: t.surface }]}>
      <Text style={{ color: t.text, fontWeight: "600" }}>{total} listings</Text>

      <View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Sort by"
          accessibilityState={{ expanded: sortOpen }}
          onPress={() => setSortOpen((o) => !o)}
          style={[styles.btn, { borderColor: t.border }]}
        >
          <Text style={{ color: t.text }}>Sort: {SORT_LABEL[sort]} ▾</Text>
        </Pressable>
        {sortOpen && (
          <>
            {/* Backdrop closes the menu on outside click. Sized large so
                taps anywhere outside the menu register, but it stays
                under the menu z-index. */}
            <Pressable
              accessibilityElementsHidden
              importantForAccessibility="no-hide-descendants"
              onPress={() => setSortOpen(false)}
              style={styles.backdrop}
            />
            <View
              accessibilityRole="menu"
              style={[styles.menu, { backgroundColor: t.surface, borderColor: t.border }]}
            >
              {SORT_OPTIONS.map((opt) => {
                const active =
                  opt.value === sort ||
                  // Treat the legacy "bedrooms" alias as bedrooms_desc when
                  // highlighting the active option.
                  (sort === "bedrooms" && opt.value === "bedrooms_desc");
                return (
                  <Pressable
                    key={opt.value}
                    accessibilityRole="menuitem"
                    accessibilityLabel={`Sort by ${opt.label}`}
                    accessibilityState={{ selected: active }}
                    onPress={() => {
                      onSortChange(opt.value);
                      setSortOpen(false);
                    }}
                    style={[
                      styles.menuItem,
                      active && { backgroundColor: t.surfaceAlt },
                    ]}
                  >
                    <Text style={{ color: active ? t.accent : t.text }}>
                      {opt.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </>
        )}
      </View>

      {onSave && canSave && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Save this search"
          onPress={onSave}
          style={[styles.btn, { borderColor: t.border }]}
        >
          <Text style={{ color: t.text }}>★ Save</Text>
        </Pressable>
      )}
      {onOpenSaved && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Open saved searches"
          onPress={onOpenSaved}
          style={[styles.btn, { borderColor: t.border }]}
        >
          <Text style={{ color: t.text }}>Saved</Text>
        </Pressable>
      )}
      {/* Issue #121 — compare button appears once 2+ listings are ticked. */}
      {onCompare && compareCount >= 2 && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Compare ${compareCount} listings`}
          onPress={onCompare}
          style={[
            styles.btn,
            { borderColor: t.accent, backgroundColor: t.accent },
          ]}
        >
          <Text style={{ color: "#fff", fontWeight: "700" }}>
            ⇄ Compare ({compareCount})
          </Text>
        </Pressable>
      )}

      <View style={styles.switcherWrap}>
        <View style={styles.switcher}>
          <ViewBtn label="Cards" active={view === "cards"} onPress={() => onViewChange("cards")} />
          <ViewBtn label="List" active={view === "list"} onPress={() => onViewChange("list")} />
          <ViewBtn label="Map" active={view === "map"} onPress={() => onViewChange("map")} />
          <ViewBtn label="Split" active={view === "split"} onPress={() => onViewChange("split")} />
        </View>
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

const styles = StyleSheet.create({
  row: {
    flexDirection: "row", alignItems: "center", gap: 12,
    padding: 10, borderWidth: 1, borderRadius: 8, flexWrap: "wrap",
    // Allow the absolute-positioned sort menu to escape the row's bounds.
    position: "relative",
    zIndex: 10,
  },
  switcherWrap: { marginLeft: "auto", alignItems: "center", gap: 4 },
  switcher: { flexDirection: "row", gap: 6 },
  btn: { paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderRadius: 6 },
  backdrop: {
    position: "absolute",
    top: -1000, left: -2000, right: -2000, bottom: -1000,
    zIndex: 20,
  },
  menu: {
    position: "absolute",
    top: "100%", left: 0,
    marginTop: 4,
    minWidth: 180,
    borderWidth: 1,
    borderRadius: 6,
    paddingVertical: 4,
    zIndex: 30,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    boxShadow: ("0 4px 12px rgba(0,0,0,0.12)" as any),
  },
  menuItem: { paddingHorizontal: 12, paddingVertical: 8 },
});
