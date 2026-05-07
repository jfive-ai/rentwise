import React, { useCallback, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
import type { NormalizedQuery } from "@/src/api/types";
import { useTheme } from "@/src/theme";
import { buildSearchUrls, type SourceLaunchPlan } from "./buildSearchUrls";

interface Props {
  query: NormalizedQuery;
  /** Called when the user fires the launcher (after tabs open). */
  onLaunched?: () => void;
}

type State =
  | { kind: "idle" }
  | { kind: "launched"; plans: SourceLaunchPlan[]; blocked: SourceLaunchPlan[] }
  | { kind: "non_web" };

/**
 * Opens one tab per enabled source, synchronously inside the click
 * handler. Modern Chrome accepts back-to-back `window.open` calls in
 * the same gesture chain; if any return null we fall back to surfacing
 * an "Allow popups" hint inline.
 *
 * Web-only: native (iOS/macOS) builds show a hint that the launcher
 * relies on a desktop browser extension.
 */
export function LauncherButton({ query, onLaunched }: Props) {
  const t = useTheme();
  const [state, setState] = useState<State>({ kind: "idle" });

  const onPress = useCallback(() => {
    if (Platform.OS !== "web") {
      setState({ kind: "non_web" });
      return;
    }
    if (typeof window === "undefined") return;
    const plans = buildSearchUrls(query);
    const blocked: SourceLaunchPlan[] = [];
    for (const plan of plans) {
      const w = window.open(plan.url, "_blank", "noopener,noreferrer");
      if (!w) blocked.push(plan);
    }
    setState({ kind: "launched", plans, blocked });
    onLaunched?.();
  }, [query, onLaunched]);

  const enabledCount = buildSearchUrls(query).length;

  return (
    <View style={styles.wrap}>
      <Pressable
        accessibilityRole="button"
        onPress={onPress}
        style={[styles.primary, { backgroundColor: t.accent }]}
      >
        <Text style={styles.primaryText}>
          Search across sources ({enabledCount} sites)
        </Text>
      </Pressable>

      {state.kind === "launched" && state.blocked.length === 0 && (
        <Text style={[styles.hint, { color: t.textMuted }]}>
          Opened {state.plans.length} tab(s). Captured listings appear here within seconds.
        </Text>
      )}

      {state.kind === "launched" && state.blocked.length > 0 && (
        <View
          style={[styles.warn, { borderColor: t.border, backgroundColor: t.surface }]}
        >
          <Text style={{ color: "#a30", fontWeight: "600" }}>
            Popup blocker prevented {state.blocked.length} of {state.plans.length} tab(s).
          </Text>
          <Text style={[styles.hint, { color: t.textMuted, marginTop: 4 }]}>
            Allow popups for this site in your browser, then click again. Blocked: {" "}
            {state.blocked.map((p) => p.label).join(", ")}.
          </Text>
        </View>
      )}

      {state.kind === "non_web" && (
        <View
          style={[styles.warn, { borderColor: t.border, backgroundColor: t.surface }]}
        >
          <Text style={{ color: t.text }}>
            The launcher needs a desktop browser with the RentWise Capture extension
            installed.
          </Text>
        </View>
      )}

      {/* Per-source unsupported-filter notes */}
      {(() => {
        const plans = buildSearchUrls(query);
        const withUnsupported = plans.filter((p) => p.unsupported.length > 0);
        if (withUnsupported.length === 0) return null;
        return (
          <View style={[styles.notes, { borderColor: t.border }]}>
            {withUnsupported.map((p) => (
              <Text key={p.id} style={[styles.note, { color: t.textMuted }]}>
                {p.label} won&apos;t filter on: {p.unsupported.join(", ")}
              </Text>
            ))}
          </View>
        );
      })()}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8 },
  primary: { paddingHorizontal: 18, paddingVertical: 12, borderRadius: 8, alignItems: "center" },
  primaryText: { color: "#fff", fontWeight: "600" },
  hint: { fontSize: 12 },
  warn: { padding: 10, borderWidth: 1, borderRadius: 8 },
  notes: { borderTopWidth: 1, paddingTop: 6, gap: 2 },
  note: { fontSize: 11 },
});
