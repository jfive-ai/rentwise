import React, { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { searchClient } from "@/src/api/client";
import { useQuery } from "@/src/state/QueryProvider";
import { useTheme } from "@/src/theme";

interface Props {
  apiBaseUrl: string;
}

export function NLSearchBar({ apiBaseUrl }: Props) {
  const t = useTheme();
  const { nlText, setNlText, set, reset, setMode } = useQuery();
  const client = useMemo(() => searchClient(apiBaseUrl), [apiBaseUrl]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onParse = useCallback(async () => {
    const text = nlText.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      const result = await client.translateQuery({ text });
      // Replace structured query with the LLM's interpretation; chips reflect
      // only what the LLM parsed, not stale filters from a previous mode.
      reset();
      set(result.query);
    } catch {
      setError(
        "LLM unavailable — switched to filter mode. Try again or use the filter UI."
      );
      setMode("filters");
    } finally {
      setBusy(false);
    }
  }, [client, nlText, reset, set, setMode]);

  // Only block on in-flight requests. The empty-text guard lives in onParse
  // (so a press with empty input is a silent no-op). Coupling `disabled` to
  // `nlText` length raced with React's batching in CI: a press dispatched
  // between fireEvent.changeText and the next reconcile saw `disabled=true`
  // and was silently dropped.
  const disabled = busy;

  return (
    <View
      style={[
        styles.wrap,
        { borderColor: t.border, backgroundColor: t.surface },
      ]}
    >
      <TextInput
        accessibilityLabel="Search input"
        placeholder="Try: 2 bedroom in Kitsilano under 3000 pet ok"
        placeholderTextColor={t.textMuted}
        value={nlText}
        onChangeText={setNlText}
        editable={!busy}
        multiline
        style={[styles.input, { color: t.text, borderColor: t.border }]}
      />
      <View style={styles.row}>
        <Pressable
          accessibilityRole="button"
          onPress={onParse}
          disabled={disabled}
          style={[
            styles.parseBtn,
            { backgroundColor: busy ? t.textMuted : t.accent },
          ]}
        >
          {busy ? (
            <View style={styles.btnInner}>
              <ActivityIndicator size="small" color="#fff" />
              <Text style={styles.parseBtnText}>Parsing…</Text>
            </View>
          ) : (
            <Text style={styles.parseBtnText}>Parse</Text>
          )}
        </Pressable>
      </View>
      {error ? <Text style={[styles.error, { color: "#c00" }]}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 12, borderWidth: 1, borderRadius: 8, gap: 8 },
  input: {
    minHeight: 56,
    padding: 8,
    borderWidth: 1,
    borderRadius: 6,
    textAlignVertical: "top",
  },
  row: { flexDirection: "row", justifyContent: "flex-end" },
  btnInner: { flexDirection: "row", alignItems: "center", gap: 6 },
  parseBtn: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 6 },
  parseBtnText: { color: "#fff", fontWeight: "600" },
  error: { marginTop: 4, fontSize: 13 },
});
