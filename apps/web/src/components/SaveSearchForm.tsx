/**
 * Phase 5 PR-A: small inline form for saving the current search.
 *
 * Renders as a dismissible card the SearchScreen mounts above the
 * results list when the user clicks ★ Save. POSTs to /searches and
 * fires onSaved() so the parent can refresh the drawer's cached list.
 */

import React, { useState } from "react";
import {
  Pressable,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import type { ApiClient } from "@/src/api/client";
import type { NormalizedQuery } from "@/src/api/types";
import { useTheme } from "@/src/theme";

interface Props {
  client: ApiClient;
  query: NormalizedQuery;
  onSaved: () => void;
  onCancel: () => void;
}

type State =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export function SaveSearchForm({ client, query, onSaved, onCancel }: Props) {
  const t = useTheme();
  const [label, setLabel] = useState("");
  const [alertEnabled, setAlertEnabled] = useState(false);
  const [email, setEmail] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  const submit = async () => {
    setState({ kind: "saving" });
    try {
      await client.saveSearch({
        query,
        label: label.trim() === "" ? null : label.trim(),
        alert_enabled: alertEnabled,
        alert_email:
          alertEnabled && email.trim() !== "" ? email.trim() : null,
      });
      setState({ kind: "ok" });
      onSaved();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setState({ kind: "error", message: msg });
    }
  };

  return (
    <View style={[styles.card, { borderColor: t.border, backgroundColor: t.surface }]}>
      <Text style={[styles.title, { color: t.text }]}>Save this search</Text>

      <Text style={[styles.label, { color: t.textMuted }]}>Label</Text>
      <TextInput
        accessibilityLabel="Saved search label"
        placeholder="e.g. 2br Kits under $3000"
        placeholderTextColor={t.textMuted}
        value={label}
        onChangeText={setLabel}
        style={[styles.input, { color: t.text, borderColor: t.border }]}
      />

      <View style={styles.alertRow}>
        <Switch
          accessibilityLabel="Email me when new listings match"
          value={alertEnabled}
          onValueChange={setAlertEnabled}
        />
        <Text style={{ color: t.text }}>Email me when new listings match</Text>
      </View>

      {alertEnabled && (
        <>
          <Text style={[styles.label, { color: t.textMuted }]}>Email</Text>
          <TextInput
            accessibilityLabel="Alert email"
            placeholder="you@example.com"
            placeholderTextColor={t.textMuted}
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            style={[styles.input, { color: t.text, borderColor: t.border }]}
          />
        </>
      )}

      {state.kind === "error" && (
        <Text style={{ color: "#a30", marginTop: 4 }}>
          Couldn&apos;t save: {state.message}
        </Text>
      )}

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Cancel save"
          onPress={onCancel}
          style={[styles.btn, { borderColor: t.border }]}
        >
          <Text style={{ color: t.text }}>Cancel</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Confirm save"
          onPress={() => void submit()}
          disabled={state.kind === "saving"}
          style={[styles.btn, { borderColor: t.border, backgroundColor: t.accent }]}
        >
          <Text style={{ color: "#fff" }}>
            {state.kind === "saving" ? "Saving…" : "Save"}
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { padding: 16, borderWidth: 1, borderRadius: 8, gap: 8 },
  title: { fontSize: 14, fontWeight: "600" },
  label: { fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 },
  input: { borderWidth: 1, borderRadius: 6, padding: 8 },
  alertRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 4 },
  actions: { flexDirection: "row", gap: 8, marginTop: 8, justifyContent: "flex-end" },
  btn: { paddingHorizontal: 14, paddingVertical: 8, borderWidth: 1, borderRadius: 6 },
});
