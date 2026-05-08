import React from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import type { AdapterHealth } from "@/src/api/types";
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
    <View style={{ gap: 12 }} accessibilityRole="alert" accessibilityLabel="Searching for listings">
      <View style={[styles.searchingPill, { borderColor: t.border, backgroundColor: t.surface }]}>
        <ActivityIndicator size="small" color={t.accent} />
        <Text style={{ color: t.text, fontWeight: "600" }}>Searching…</Text>
      </View>
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

/** Trim multi-line provider error blobs (e.g. LiteLLM stack traces) to one line. */
function summarizeAdapterError(raw: string | null): string {
  if (!raw) return "(no detail)";
  const firstLine = raw.split(/\r?\n/, 1)[0]!.trim();
  return firstLine.length > 200 ? firstLine.slice(0, 197) + "…" : firstLine;
}

/**
 * Surface adapter failures the API reports via `source_health`. Renders only
 * when at least one source isn't `ok`. The previous UX showed "No listings
 * matched your filters" even when *every* enabled adapter had failed (e.g.
 * Craigslist 403 from non-residential IPs), which made search look broken.
 */
export function AdapterFailureBanner({
  sourceHealth,
}: {
  sourceHealth: Record<string, AdapterHealth>;
}) {
  const t = useTheme();
  const failing = Object.values(sourceHealth).filter((h) => h.status !== "ok");
  if (failing.length === 0) return null;
  return (
    <View
      style={[styles.box, { borderColor: t.warn, backgroundColor: t.surface }]}
      accessibilityRole="alert"
    >
      <Text style={{ color: t.warn, fontWeight: "600", marginBottom: 4 }}>
        {failing.length === 1
          ? `Source unavailable: ${failing[0]!.name}`
          : `${failing.length} sources unavailable`}
      </Text>
      {failing.map((h) => (
        <Text key={h.name} style={{ color: t.text, fontSize: 13 }}>
          • {h.name} ({h.status}): {summarizeAdapterError(h.last_error)}
        </Text>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderWidth: 1, borderRadius: 8, padding: 16 },
  btn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderWidth: 1,
    borderRadius: 6,
    alignSelf: "flex-start",
  },
  skeleton: { height: 80, borderRadius: 8, opacity: 0.5 },
  searchingPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1,
    borderRadius: 999,
    alignSelf: "flex-start",
  },
});
