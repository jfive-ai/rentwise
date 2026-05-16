import React from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import type { NormalizedListing, SortOrder } from "@/src/api/types";
import type { ActionFlag, ListingActionMap, ListingActions } from "@/src/storage/listingActions";
import { openExternalUrl } from "@/src/lib/openUrl";
import { useTheme } from "@/src/theme";

const ROW_HEIGHT = 56;

// Each sortable column has a default direction (the one chosen on the
// first click) and a paired opposite direction (used when the user
// clicks the already-active column to toggle).
const COLUMN_SORTS: Record<
  "title" | "price" | "bedrooms" | "source",
  { default: SortOrder; opposite: SortOrder; matches: SortOrder[] }
> = {
  title: {
    default: "title_asc",
    opposite: "title_desc",
    matches: ["title_asc", "title_desc"],
  },
  price: {
    default: "price_asc",
    opposite: "price_desc",
    matches: ["price_asc", "price_desc"],
  },
  bedrooms: {
    default: "bedrooms_desc",
    opposite: "bedrooms_asc",
    // The legacy "bedrooms" alias maps to bedrooms_desc.
    matches: ["bedrooms_asc", "bedrooms_desc", "bedrooms"],
  },
  source: {
    default: "source_asc",
    opposite: "source_desc",
    matches: ["source_asc", "source_desc"],
  },
};

function nextForColumn(col: keyof typeof COLUMN_SORTS, current: SortOrder): SortOrder {
  const cfg = COLUMN_SORTS[col];
  if (!cfg.matches.includes(current)) return cfg.default;
  // Active column: flip direction. Treat the legacy "bedrooms" alias as
  // bedrooms_desc when computing the flip.
  const normalized = current === "bedrooms" ? "bedrooms_desc" : current;
  return normalized === cfg.default ? cfg.opposite : cfg.default;
}

function arrowFor(col: keyof typeof COLUMN_SORTS, current: SortOrder): string {
  const cfg = COLUMN_SORTS[col];
  if (!cfg.matches.includes(current)) return "";
  const normalized = current === "bedrooms" ? "bedrooms_desc" : current;
  return normalized.endsWith("_asc") ? " ↑" : " ↓";
}

interface Props {
  listings: NormalizedListing[];
  sort: SortOrder;
  onSortChange: (s: SortOrder) => void;
  actions: ListingActionMap;
  onAction: (id: string, flag: ActionFlag, value: boolean) => void;
  /** Phase 7 PR-B: split-view selection sync. */
  selectedListingId?: string | null;
  onSelectListing?: (id: string) => void;
  onHoverListing?: (id: string | null) => void;
}

export function ListingTable({
  listings,
  sort,
  onSortChange,
  actions,
  onAction,
  selectedListingId = null,
  onSelectListing,
  onHoverListing,
}: Props) {
  const t = useTheme();

  return (
    <View style={[styles.wrap, { borderColor: t.border, backgroundColor: t.surface }]}>
      <View style={[styles.headerRow, { borderColor: t.border }]}>
        <Header
          label="Title"
          column="title"
          sort={sort}
          onPress={() => onSortChange(nextForColumn("title", sort))}
        />
        <Header
          label="Price"
          column="price"
          sort={sort}
          onPress={() => onSortChange(nextForColumn("price", sort))}
        />
        <Header
          label="Beds"
          column="bedrooms"
          sort={sort}
          onPress={() => onSortChange(nextForColumn("bedrooms", sort))}
        />
        <Header
          label="Source"
          column="source"
          sort={sort}
          onPress={() => onSortChange(nextForColumn("source", sort))}
        />
        <Header label="Match" />
        <Header label="" />
      </View>
      <FlatList
        data={listings}
        keyExtractor={(item) => item.id}
        getItemLayout={(_, i) => ({ length: ROW_HEIGHT, offset: ROW_HEIGHT * i, index: i })}
        renderItem={({ item }) => (
          <Row
            listing={item}
            acts={actions[item.id] ?? {}}
            onAction={(f, v) => onAction(item.id, f, v)}
            selected={item.id === selectedListingId}
            onSelect={onSelectListing}
            onHover={onHoverListing}
          />
        )}
      />
    </View>
  );
}

function Header({
  label,
  column,
  sort,
  onPress,
}: {
  label: string;
  column?: keyof typeof COLUMN_SORTS;
  sort?: SortOrder;
  onPress?: () => void;
}) {
  const t = useTheme();
  const active = !!(column && sort && COLUMN_SORTS[column].matches.includes(sort));
  const arrow = column && sort ? arrowFor(column, sort) : "";
  if (onPress) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Sort by ${label}`}
        accessibilityState={{ selected: active }}
        onPress={onPress}
        style={styles.cell}
      >
        <Text style={{ color: active ? t.accent : t.textMuted, fontWeight: "600" }}>
          {label}
          {arrow}
        </Text>
      </Pressable>
    );
  }
  return (
    <View style={styles.cell}>
      <Text style={{ color: t.textMuted, fontWeight: "600" }}>{label}</Text>
    </View>
  );
}

function Row({
  listing,
  acts,
  onAction,
  selected,
  onSelect,
  onHover,
}: {
  listing: NormalizedListing;
  acts: ListingActions;
  onAction: (f: ActionFlag, v: boolean) => void;
  selected: boolean;
  onSelect?: (id: string) => void;
  onHover?: (id: string | null) => void;
}) {
  const t = useTheme();
  // Pressable wraps the row so click anywhere outside the action
  // buttons selects it (the Save / Open buttons stop propagation by
  // having their own onPress). Web hover events arrive via
  // onPointerEnter / onPointerLeave through react-native-web.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const hoverProps: any = onHover
    ? {
        onPointerEnter: () => onHover(listing.id),
        onPointerLeave: () => onHover(null),
      }
    : {};
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Select ${listing.title}`}
      onPress={() => onSelect?.(listing.id)}
      style={[
        styles.row,
        {
          height: ROW_HEIGHT,
          borderColor: t.border,
          backgroundColor: selected ? t.surfaceAlt : "transparent",
        },
      ]}
      {...hoverProps}
    >
      <View style={styles.cell}>
        <Text numberOfLines={1} style={{ color: t.text }}>{listing.title}</Text>
      </View>
      <View style={styles.cell}>
        <Text style={{ color: t.text }}>
          {listing.price_cad == null ? "—" : `$${listing.price_cad.toLocaleString("en-CA")}`}
        </Text>
      </View>
      <View style={styles.cell}>
        <Text style={{ color: t.text }}>{listing.bedrooms ?? "—"}</Text>
      </View>
      <View style={styles.cell}>
        <Text style={{ color: t.textMuted }}>{listing.source}</Text>
      </View>
      <View style={styles.cell}>
        {listing.match_score != null ? (
          <Text
            style={{
              color:
                listing.match_score >= 80
                  ? "#16a34a"
                  : listing.match_score >= 60
                    ? "#d97706"
                    : t.textMuted,
              fontWeight: "700",
            }}
          >
            {listing.match_score}
          </Text>
        ) : (
          <Text style={{ color: t.textMuted }}>—</Text>
        )}
      </View>
      <View style={[styles.cell, styles.actionsCell]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Save" onPress={() => onAction("saved", !acts.saved)}>
          <Text style={{ color: acts.saved ? t.accent : t.textMuted }}>♥</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Open original" onPress={() => openExternalUrl(listing.source_url)}>
          <Text style={{ color: t.textMuted }}>↗</Text>
        </Pressable>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { borderWidth: 1, borderRadius: 8, flex: 1 },
  headerRow: { flexDirection: "row", borderBottomWidth: 1, paddingVertical: 8 },
  row: { flexDirection: "row", alignItems: "center", borderBottomWidth: 1 },
  cell: { flex: 1, paddingHorizontal: 10, justifyContent: "center" },
  actionsCell: { flexDirection: "row", gap: 12, flex: 0.5 },
});
