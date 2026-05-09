import React, { useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";
import type { NormalizedListing } from "@/src/api/types";
import type { ActionFlag, ListingActions } from "@/src/storage/listingActions";
import { openExternalUrl } from "@/src/lib/openUrl";
import { useTheme } from "@/src/theme";

interface Props {
  listing: NormalizedListing;
  actions: ListingActions;
  onAction: (flag: ActionFlag, value: boolean) => void;
  /**
   * Other listings sharing this card's canonical_id (Phase 4 PR-D).
   * Renders collapsed under "Also on N source(s)"; the user can expand
   * for a per-source link list.
   */
  alternates?: NormalizedListing[];
}

const formatPrice = (n: number | null): string =>
  n == null ? "—" : `$${n.toLocaleString("en-CA")}`;

export function ListingCard({ listing, actions, onAction, alternates }: Props) {
  const t = useTheme();
  const [expanded, setExpanded] = useState(false);
  const photo = listing.photos[0];
  const alts = alternates ?? [];
  const hasAlts = alts.length > 0;
  return (
    <View style={[styles.card, { backgroundColor: t.surface, borderColor: t.border }]}>
      <View style={[styles.photo, { backgroundColor: t.surfaceAlt }]}>
        {photo ? (
          <Image source={{ uri: photo }} style={StyleSheet.absoluteFill} resizeMode="cover" />
        ) : (
          <Text style={{ color: t.textMuted }}>No photo</Text>
        )}
        <View style={[styles.badge, { backgroundColor: t.surface }]}>
          <Text style={{ color: t.textMuted, fontSize: 11 }}>{listing.source}</Text>
        </View>
      </View>

      <View style={styles.body}>
        <Text style={[styles.title, { color: t.text }]} numberOfLines={2}>{listing.title}</Text>
        <View style={styles.metaRow}>
          <Text style={[styles.price, { color: t.text }]}>{formatPrice(listing.price_cad)}</Text>
          {listing.bedrooms != null && <Text style={{ color: t.textMuted }}>{listing.bedrooms} bd</Text>}
          {listing.address && <Text style={{ color: t.textMuted }} numberOfLines={1}>{listing.address}</Text>}
        </View>
        {listing.description_snippet && (
          <Text style={{ color: t.textMuted }} numberOfLines={2}>{listing.description_snippet}</Text>
        )}

        {hasAlts && (
          <View style={styles.duplicateBlock}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={
                expanded
                  ? "Hide duplicate sources"
                  : `Show ${alts.length} duplicate source${alts.length === 1 ? "" : "s"}`
              }
              onPress={() => setExpanded((v) => !v)}
            >
              <Text style={{ color: t.textMuted, fontSize: 12 }}>
                Also on {alts.length} source{alts.length === 1 ? "" : "s"}
                {expanded ? " ▴" : " ▾"}
              </Text>
            </Pressable>
            {expanded && (
              <View style={styles.duplicateList}>
                {alts.map((alt) => (
                  <Pressable
                    key={alt.id}
                    accessibilityRole="button"
                    accessibilityLabel={`Open ${alt.source}`}
                    onPress={() => openExternalUrl(alt.source_url)}
                  >
                    <Text style={{ color: t.text, fontSize: 12 }}>↗ {alt.source}</Text>
                  </Pressable>
                ))}
              </View>
            )}
          </View>
        )}

        <View style={styles.actions}>
          <ActionBtn label="Save" active={!!actions.saved} onPress={() => onAction("saved", !actions.saved)} />
          <ActionBtn label="Hide" active={!!actions.hidden} onPress={() => onAction("hidden", !actions.hidden)} />
          <ActionBtn label="Contacted" active={!!actions.contacted} onPress={() => onAction("contacted", !actions.contacted)} />
          <ActionBtn
            label="Open original"
            active={false}
            onPress={() => openExternalUrl(listing.source_url)}
          />
        </View>
      </View>
    </View>
  );
}

function ActionBtn({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={[styles.actionBtn, { borderColor: t.border, backgroundColor: active ? t.accent : "transparent" }]}
    >
      <Text style={{ color: active ? "#fff" : t.text, fontSize: 12 }}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: 12, overflow: "hidden", flexBasis: 320, flexGrow: 1 },
  photo: { aspectRatio: 16 / 9, alignItems: "center", justifyContent: "center" },
  badge: { position: "absolute", left: 8, top: 8, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999 },
  body: { padding: 12, gap: 6 },
  title: { fontSize: 15, fontWeight: "600" },
  metaRow: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  price: { fontWeight: "700" },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 8 },
  actionBtn: { paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderRadius: 6 },
  duplicateBlock: { marginTop: 4, gap: 4 },
  duplicateList: { gap: 4, paddingLeft: 12 },
});
