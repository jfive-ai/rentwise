import React, { useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useQuery } from "@/src/state/QueryProvider";
import { DisabledControl } from "@/src/components/DisabledControl";
import { LauncherButton } from "@/src/launcher/LauncherButton";
import { useTheme } from "@/src/theme";

const BEDROOM_CHIPS = [
  { label: "Studio", value: 0.5 },
  { label: "1", value: 1 },
  { label: "2", value: 2 },
  { label: "3", value: 3 },
  { label: "4+", value: 4 },
];

export const NEIGHBORHOODS = [
  "Coal Harbour", "Commercial Drive", "Downtown", "Dunbar",
  "East Vancouver", "Fairview", "False Creek", "Gastown",
  "Grandview-Woodland", "Kerrisdale", "Kitsilano", "Marpole",
  "Mount Pleasant", "Oakridge", "Point Grey", "Riley Park",
  "Shaughnessy", "South Cambie", "South Granville", "Strathcona",
  "Sunset", "West End", "West Point Grey", "Yaletown",
];

interface Props {
  onSearch: () => void;
  /** Optional callback fired after the user clicks "Search across sources". */
  onLauncherFired?: () => void;
}

export function FilterPanel({ onSearch, onLauncherFired }: Props) {
  const { query, set, reset, toggleNeighborhood, toggleKeyword } = useQuery();
  const t = useTheme();
  const [kw, setKw] = useState("");

  const selectedNeighborhoods = query.neighborhoods;
  const [neighborhoodsOpen, setNeighborhoodsOpen] = useState(false);

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={[styles.wrap, { backgroundColor: t.bg }]}
    >
      <Section title="Bedrooms" theme={t}>
        <View style={styles.chipRow}>
          {BEDROOM_CHIPS.map((c) => {
            const selected = query.bedrooms_min === c.value;
            return (
              <Pressable
                key={c.label}
                accessibilityRole="button"
                onPress={() =>
                  set({ bedrooms_min: selected ? null : c.value })
                }
                style={[
                  styles.chip,
                  { borderColor: t.border, backgroundColor: selected ? t.accent : t.surface },
                ]}
              >
                <Text style={{ color: selected ? "#fff" : t.text }}>{c.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </Section>

      <Section title="Price (CAD/mo)" theme={t}>
        <View style={styles.row}>
          <TextInput
            placeholder="Min"
            placeholderTextColor={t.textMuted}
            keyboardType="numeric"
            value={query.price_min?.toString() ?? ""}
            onChangeText={(v) => set({ price_min: toIntOrNull(v) })}
            style={[styles.input, { color: t.text, borderColor: t.border }]}
          />
          <TextInput
            placeholder="Max"
            placeholderTextColor={t.textMuted}
            keyboardType="numeric"
            value={query.price_max?.toString() ?? ""}
            onChangeText={(v) => set({ price_max: toIntOrNull(v) })}
            style={[styles.input, { color: t.text, borderColor: t.border }]}
          />
        </View>
      </Section>

      <Section
        title={
          selectedNeighborhoods.length > 0
            ? `Neighborhoods (${selectedNeighborhoods.length} selected)`
            : "Neighborhoods"
        }
        theme={t}
      >
        {/* Collapsed state: show selected chips inline (each click clears
            it) plus an "Edit" affordance. The full grid appears only
            when the user explicitly opens it, so the panel doesn't
            blow up to 24 chips by default. */}
        {!neighborhoodsOpen && (
          <View style={styles.chipRow}>
            {selectedNeighborhoods.map((n) => (
              <Pressable
                key={n}
                accessibilityRole="button"
                accessibilityLabel={`Remove ${n}`}
                onPress={() => toggleNeighborhood(n)}
                style={[styles.chip, { borderColor: t.border, backgroundColor: t.accent }]}
              >
                <Text style={{ color: "#fff" }}>{n} ✕</Text>
              </Pressable>
            ))}
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={
                selectedNeighborhoods.length > 0
                  ? "Edit neighborhoods"
                  : "Choose neighborhoods"
              }
              onPress={() => setNeighborhoodsOpen(true)}
              style={[styles.chip, { borderColor: t.border, backgroundColor: t.surface }]}
            >
              <Text style={{ color: t.text }}>
                {selectedNeighborhoods.length > 0
                  ? "Edit"
                  : `Choose (${NEIGHBORHOODS.length})`}
              </Text>
            </Pressable>
          </View>
        )}

        {neighborhoodsOpen && (
          <>
            <View style={styles.chipRow}>
              {NEIGHBORHOODS.map((n) => {
                const selected = selectedNeighborhoods.includes(n);
                return (
                  <Pressable
                    key={n}
                    accessibilityRole="button"
                    onPress={() => toggleNeighborhood(n)}
                    style={[
                      styles.chip,
                      {
                        borderColor: t.border,
                        backgroundColor: selected ? t.accent : t.surface,
                      },
                    ]}
                  >
                    <Text style={{ color: selected ? "#fff" : t.text }}>{n}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Done editing neighborhoods"
              onPress={() => setNeighborhoodsOpen(false)}
              style={[styles.doneBtn, { borderColor: t.border }]}
            >
              <Text style={{ color: t.text }}>Done</Text>
            </Pressable>
          </>
        )}
      </Section>

      <Section title="Keywords" theme={t}>
        <TextInput
          placeholder="Add keyword and press Enter"
          placeholderTextColor={t.textMuted}
          value={kw}
          onChangeText={setKw}
          onSubmitEditing={(e) => {
            const next = e.nativeEvent.text;
            if (next.trim()) toggleKeyword(next);
            setKw("");
          }}
          returnKeyType="done"
          style={[styles.input, { color: t.text, borderColor: t.border }]}
        />
        <View style={styles.chipRow}>
          {query.free_text_keywords.map((k) => (
            <Pressable
              key={k}
              accessibilityRole="button"
              onPress={() => toggleKeyword(k)}
              style={[styles.chip, { borderColor: t.border, backgroundColor: t.surface }]}
            >
              <Text style={{ color: t.text }}>{k} ✕</Text>
            </Pressable>
          ))}
        </View>
      </Section>

      <Section title="School catchment" theme={t}>
        <TextInput
          placeholder="e.g. Lord Byng"
          placeholderTextColor={t.textMuted}
          value={query.school_catchment ?? ""}
          onChangeText={(v) => set({ school_catchment: v.trim() === "" ? null : v })}
          accessibilityLabel="School catchment"
          style={[styles.input, { color: t.text, borderColor: t.border }]}
        />
      </Section>

      <Section title="Transit walk (max min)" theme={t}>
        <TextInput
          placeholder="e.g. 10"
          placeholderTextColor={t.textMuted}
          keyboardType="numeric"
          value={query.transit_max_walk_minutes?.toString() ?? ""}
          onChangeText={(v) => set({ transit_max_walk_minutes: toClampedMinutes(v) })}
          accessibilityLabel="Transit walk minutes"
          style={[styles.input, { color: t.text, borderColor: t.border }]}
        />
      </Section>

      <DisabledControl label="Pets" phase="Phase 3 — more sources">
        <Text style={{ color: t.textMuted }}>Required · Allowed · Not allowed · Any</Text>
      </DisabledControl>
      <DisabledControl label="Furnished" phase="Phase 3">
        <Text style={{ color: t.textMuted }}>Yes · No · Any</Text>
      </DisabledControl>
      <DisabledControl label="Available after" phase="Phase 3">
        <Text style={{ color: t.textMuted }}>YYYY-MM-DD</Text>
      </DisabledControl>

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          onPress={onSearch}
          style={[styles.primary, { backgroundColor: t.accent }]}
        >
          <Text style={styles.primaryText}>Search</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={reset}
          style={[styles.secondary, { borderColor: t.border }]}
        >
          <Text style={{ color: t.text }}>Reset</Text>
        </Pressable>
      </View>

      <View style={styles.launcher}>
        <LauncherButton query={query} onLaunched={onLauncherFired} />
      </View>
    </ScrollView>
  );
}

function Section({
  title,
  children,
  theme: t,
}: {
  title: string;
  children: React.ReactNode;
  theme: ReturnType<typeof useTheme>;
}) {
  return (
    <View style={styles.section}>
      <Text style={[styles.sectionLabel, { color: t.textMuted }]}>{title}</Text>
      {children}
    </View>
  );
}

function toIntOrNull(v: string): number | null {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : null;
}

/** 1-30 minute bound; out-of-range or unparseable input → null. */
function toClampedMinutes(v: string): number | null {
  const n = parseInt(v, 10);
  if (!Number.isFinite(n)) return null;
  if (n < 1 || n > 30) return null;
  return n;
}

const styles = StyleSheet.create({
  // flex: 1 → the ScrollView fills its bounded parent height (set by
  // SearchScreen's `filters` style). Without this, the ScrollView
  // sizes to its content and there's nothing to scroll within.
  scroll: { flex: 1 },
  wrap: { padding: 16, gap: 16 },
  section: { gap: 8 },
  sectionLabel: { fontSize: 12, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.6 },
  row: { flexDirection: "row", gap: 8 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderRadius: 999 },
  input: { flex: 1, borderWidth: 1, borderRadius: 8, padding: 10 },
  doneBtn: {
    alignSelf: "flex-start",
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderWidth: 1,
    borderRadius: 6,
    marginTop: 4,
  },
  actions: { flexDirection: "row", gap: 8, marginTop: 8 },
  primary: { paddingHorizontal: 18, paddingVertical: 12, borderRadius: 8 },
  primaryText: { color: "#fff", fontWeight: "600" },
  secondary: { paddingHorizontal: 18, paddingVertical: 12, borderRadius: 8, borderWidth: 1 },
  launcher: { marginTop: 16, paddingTop: 16, borderTopWidth: 1, borderColor: "#e5e5e5" },
});
