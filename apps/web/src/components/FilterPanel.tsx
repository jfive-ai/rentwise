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
}

export function FilterPanel({ onSearch }: Props) {
  const { query, set, reset, toggleNeighborhood, toggleKeyword } = useQuery();
  const t = useTheme();
  const [kw, setKw] = useState("");

  return (
    <ScrollView contentContainerStyle={[styles.wrap, { backgroundColor: t.bg }]}>
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

      <Section title="Neighborhoods" theme={t}>
        <View style={styles.chipRow}>
          {NEIGHBORHOODS.map((n) => {
            const selected = query.neighborhoods.includes(n);
            return (
              <Pressable
                key={n}
                accessibilityRole="button"
                onPress={() => toggleNeighborhood(n)}
                style={[
                  styles.chip,
                  { borderColor: t.border, backgroundColor: selected ? t.accent : t.surface },
                ]}
              >
                <Text style={{ color: selected ? "#fff" : t.text }}>{n}</Text>
              </Pressable>
            );
          })}
        </View>
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

      <DisabledControl label="School catchment" phase="Phase 4 — geocoding">
        <Text style={{ color: t.textMuted }}>Lord Byng / Kitsilano Secondary / …</Text>
      </DisabledControl>
      <DisabledControl label="Pets" phase="Phase 3 — more sources">
        <Text style={{ color: t.textMuted }}>Required · Allowed · Not allowed · Any</Text>
      </DisabledControl>
      <DisabledControl label="Furnished" phase="Phase 3">
        <Text style={{ color: t.textMuted }}>Yes · No · Any</Text>
      </DisabledControl>
      <DisabledControl label="Available after" phase="Phase 3">
        <Text style={{ color: t.textMuted }}>YYYY-MM-DD</Text>
      </DisabledControl>
      <DisabledControl label="Transit walk (max min)" phase="Phase 4 — transit data">
        <Text style={{ color: t.textMuted }}>15</Text>
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

const styles = StyleSheet.create({
  wrap: { padding: 16, gap: 16 },
  section: { gap: 8 },
  sectionLabel: { fontSize: 12, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.6 },
  row: { flexDirection: "row", gap: 8 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderRadius: 999 },
  input: { flex: 1, borderWidth: 1, borderRadius: 8, padding: 10 },
  actions: { flexDirection: "row", gap: 8, marginTop: 8 },
  primary: { paddingHorizontal: 18, paddingVertical: 12, borderRadius: 8 },
  primaryText: { color: "#fff", fontWeight: "600" },
  secondary: { paddingHorizontal: 18, paddingVertical: 12, borderRadius: 8, borderWidth: 1 },
});
