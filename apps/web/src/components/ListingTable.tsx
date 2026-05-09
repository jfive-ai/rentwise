import React from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import type { NormalizedListing, SortOrder } from "@/src/api/types";
import type { ActionFlag, ListingActionMap, ListingActions } from "@/src/storage/listingActions";
import { openExternalUrl } from "@/src/lib/openUrl";
import { useTheme } from "@/src/theme";

const ROW_HEIGHT = 56;

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
        <Header label="Title" />
        <Header label="Price" sortKey="price_asc" sort={sort} onPress={() => onSortChange("price_asc")} />
        <Header label="Beds" sortKey="bedrooms" sort={sort} onPress={() => onSortChange("bedrooms")} />
        <Header label="Source" />
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
  label, sortKey, sort, onPress,
}: { label: string; sortKey?: SortOrder; sort?: SortOrder; onPress?: () => void }) {
  const t = useTheme();
  const active = sortKey && sort === sortKey;
  if (onPress) {
    return (
      <Pressable accessibilityRole="button" onPress={onPress} style={styles.cell}>
        <Text style={{ color: active ? t.accent : t.textMuted, fontWeight: "600" }}>{label}</Text>
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
