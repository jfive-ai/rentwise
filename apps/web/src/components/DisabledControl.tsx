import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTheme } from "@/src/theme";

interface Props {
  label: string;
  phase: string;
  children: React.ReactNode;
}

export function DisabledControl({ label, phase, children }: Props) {
  const t = useTheme();
  return (
    <View
      accessible
      accessibilityLabel={`${label}, disabled (${phase})`}
      accessibilityState={{ disabled: true }}
      style={[styles.wrap, { borderColor: t.border, backgroundColor: t.surface }]}
    >
      <View style={styles.headerRow}>
        <Text style={[styles.label, { color: t.disabled }]}>{label}</Text>
        <View style={[styles.badge, { backgroundColor: t.surfaceAlt }]}>
          <Text style={[styles.badgeText, { color: t.textMuted }]}>{phase}</Text>
        </View>
      </View>
      <View style={styles.body} pointerEvents="none">
        {children}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { borderWidth: 1, borderRadius: 8, padding: 12, gap: 8, opacity: 0.55 },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  label: { fontSize: 14, fontWeight: "600" },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999 },
  badgeText: { fontSize: 11 },
  body: { gap: 4 },
});
