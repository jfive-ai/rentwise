import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useTheme } from "@/src/theme";

export function EmptyState({ message }: { message: string }) {
  const t = useTheme();
  return (
    <View style={[styles.box, { borderColor: t.border, backgroundColor: t.surface }]}>
      <Text style={{ color: t.textMuted }}>{message}</Text>
    </View>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const t = useTheme();
  return (
    <View style={[styles.box, { borderColor: t.error, backgroundColor: t.surface }]}>
      <Text style={{ color: t.error, marginBottom: 8 }}>{message}</Text>
      <Pressable
        accessibilityRole="button"
        onPress={onRetry}
        style={[styles.btn, { borderColor: t.error }]}
      >
        <Text style={{ color: t.error }}>Retry</Text>
      </Pressable>
    </View>
  );
}

export function LoadingSkeleton({ rows = 6 }: { rows?: number }) {
  const t = useTheme();
  return (
    <View style={{ gap: 8 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <View
          key={i}
          accessibilityLabel="loading-row"
          style={[styles.skeleton, { backgroundColor: t.surfaceAlt }]}
        />
      ))}
    </View>
  );
}

export function UnsupportedFiltersBanner({ filters }: { filters: string[] }) {
  const t = useTheme();
  if (filters.length === 0) return null;
  return (
    <View style={[styles.box, { borderColor: t.warn, backgroundColor: t.surface }]}>
      <Text style={{ color: t.warn }}>
        Filters not supported by any source yet: {filters.join(", ")}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderWidth: 1, borderRadius: 8, padding: 16 },
  btn: { paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderRadius: 6, alignSelf: "flex-start" },
  skeleton: { height: 80, borderRadius: 8, opacity: 0.5 },
});
