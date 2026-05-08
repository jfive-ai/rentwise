import React, { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { ApiError, searchClient } from "@/src/api/client";
import { useQuery } from "@/src/state/QueryProvider";
import { useTheme } from "@/src/theme";

interface Props {
  apiBaseUrl: string;
}

function extractErrorDetail(e: unknown): string {
  if (e instanceof ApiError) {
    // FastAPI shape: { detail: { error, message } } — show the message so
    // the user can see *why* (e.g. "OpenRouter 401: No cookie auth credentials").
    const payload = e.payload as
      | { detail?: { message?: string } | string }
      | undefined;
    if (payload && typeof payload.detail === "object" && payload.detail?.message) {
      return payload.detail.message;
    }
    if (typeof payload?.detail === "string") return payload.detail;
    return e.status === 0 ? e.message : `HTTP ${e.status}`;
  }
  return e instanceof Error ? e.message : String(e);
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
    } catch (e) {
      setError(`LLM unavailable: ${extractErrorDetail(e)}`);
    } finally {
      setBusy(false);
    }
  }, [client, nlText, reset, set]);

  const onSwitchToFilters = useCallback(() => {
    setError(null);
    setMode("filters");
  }, [setMode]);

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
      {error ? (
        <View style={styles.errorWrap}>
          <Text style={[styles.error, { color: "#c00" }]} accessibilityRole="alert">
            {error}
          </Text>
          <View style={styles.errorActions}>
            <Pressable
              accessibilityRole="button"
              onPress={onSwitchToFilters}
              style={[styles.linkBtn, { borderColor: t.border }]}
            >
              <Text style={{ color: t.text }}>Use filter mode</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
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
  errorWrap: { marginTop: 4, gap: 6 },
  error: { fontSize: 13 },
  errorActions: { flexDirection: "row", gap: 8 },
  linkBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
  },
});
