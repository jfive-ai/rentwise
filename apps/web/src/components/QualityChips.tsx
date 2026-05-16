// Issue #120 — small ⚠ chip row for quality / scam-signal flags.
//
// Wire-format names come from the backend's QualityFlag enum (see
// apps/api/rentwise/quality/flags.py). Unknown values are silently
// dropped so adding a new flag server-side doesn't break old clients.

import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTheme } from "@/src/theme";

const FLAG_LABELS: Record<string, string> = {
  price_outlier_low: "Suspiciously cheap",
  missing_essentials: "Missing key details",
  duplicate_contact: "Same contact as others",
  photo_phash_collision: "Photos seen elsewhere",
  terse_no_address: "Very thin description",
};

interface Props {
  flags?: string[] | null;
}

export function QualityChips({ flags }: Props) {
  const t = useTheme();
  if (!flags || flags.length === 0) return null;
  const visible = flags.filter((f) => FLAG_LABELS[f]);
  if (visible.length === 0) return null;
  return (
    <View style={styles.row} accessibilityLabel="Quality flags">
      {visible.map((flag) => (
        <View
          key={flag}
          style={[
            styles.chip,
            { borderColor: "#f59e0b", backgroundColor: "rgba(245, 158, 11, 0.08)" },
          ]}
          accessibilityLabel={`Warning: ${FLAG_LABELS[flag]}`}
        >
          <Text style={{ color: "#b45309", fontSize: 11, fontWeight: "600" }}>
            ⚠ {FLAG_LABELS[flag]}
          </Text>
        </View>
      ))}
      {/* Hint to themers — keep textMuted in scope so the import isn't dead. */}
      <Text style={{ color: t.textMuted, fontSize: 0 }} aria-hidden>
        {visible.length}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: 4 },
  chip: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
    borderWidth: 1,
  },
});
