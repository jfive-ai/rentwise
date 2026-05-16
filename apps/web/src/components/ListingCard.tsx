import React, { useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";
import type { NormalizedListing } from "@/src/api/types";
import type { ActionFlag, ListingActions } from "@/src/storage/listingActions";
import { openExternalUrl } from "@/src/lib/openUrl";
import { QualityChips } from "@/src/components/QualityChips";
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
  /** Issue #121: ticked for side-by-side comparison. */
  compareChecked?: boolean;
  /** Issue #121: toggle the compare-tick for this card. */
  onCompareToggle?: (checked: boolean) => void;
  /** Issue #122: run a "more like this" derived search. */
  onFindSimilar?: () => void;
}

const formatPrice = (n: number | null): string =>
  n == null ? "—" : `$${n.toLocaleString("en-CA")}`;

export function ListingCard({
  listing,
  actions,
  onAction,
  alternates,
  compareChecked = false,
  onCompareToggle,
  onFindSimilar,
}: Props) {
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
        {listing.match_score != null && (
          <MatchBadge score={listing.match_score} explanation={listing.match_explanation ?? null} />
        )}
      </View>

      <View style={styles.body}>
        <Text style={[styles.title, { color: t.text }]} numberOfLines={2}>{listing.title}</Text>
        {listing.match_explanation ? (
          <Text style={{ color: t.textMuted, fontSize: 11 }} numberOfLines={2}>
            ✨ {listing.match_explanation}
          </Text>
        ) : null}
        {listing.price_position_label &&
          listing.price_position_label !== "Not enough comparables" && (
            <Text
              style={{
                color:
                  (listing.price_position_delta_pct ?? 0) < 0
                    ? "#16a34a"
                    : (listing.price_position_delta_pct ?? 0) > 0
                      ? "#b91c1c"
                      : t.textMuted,
                fontSize: 11,
                fontWeight: "600",
              }}
              numberOfLines={1}
            >
              📊 {listing.price_position_label}
            </Text>
          )}
        <QualityChips flags={listing.quality_flags} />
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
          {onCompareToggle && (
            <ActionBtn
              label={compareChecked ? "✓ Compare" : "+ Compare"}
              active={compareChecked}
              onPress={() => onCompareToggle(!compareChecked)}
            />
          )}
          <ActionBtn label="Save" active={!!actions.saved} onPress={() => onAction("saved", !actions.saved)} />
          <ActionBtn label="Hide" active={!!actions.hidden} onPress={() => onAction("hidden", !actions.hidden)} />
          <ActionBtn label="Contacted" active={!!actions.contacted} onPress={() => onAction("contacted", !actions.contacted)} />
          {onFindSimilar && (
            <ActionBtn
              label="↻ Find similar"
              active={false}
              onPress={onFindSimilar}
            />
          )}
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

/**
 * Issue #119 — small Match Score pill rendered in the photo overlay.
 * Color is bucketed (green ≥80, amber 60-79, grey <60) so the score
 * reads at a glance. Explanation appears below the score in small grey.
 */
function MatchBadge({ score, explanation }: { score: number; explanation: string | null }) {
  const t = useTheme();
  const bg =
    score >= 80 ? "#16a34a" : score >= 60 ? "#d97706" : "#6b7280";
  return (
    <View
      style={[
        styles.matchBadge,
        { backgroundColor: bg },
      ]}
      accessibilityLabel={`Match score ${score} out of 100${explanation ? `: ${explanation}` : ""}`}
    >
      <Text style={{ color: "#fff", fontWeight: "700", fontSize: 13 }}>{score}</Text>
      <Text style={{ color: "#fff", fontWeight: "500", fontSize: 10, marginLeft: 4, opacity: 0.85 }}>match</Text>
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
  matchBadge: {
    position: "absolute",
    right: 8,
    top: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    flexDirection: "row",
    alignItems: "center",
  },
  body: { padding: 12, gap: 6 },
  title: { fontSize: 15, fontWeight: "600" },
  metaRow: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  price: { fontWeight: "700" },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 8 },
  actionBtn: { paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderRadius: 6 },
  duplicateBlock: { marginTop: 4, gap: 4 },
  duplicateList: { gap: 4, paddingLeft: 12 },
});
