import React, { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { searchClient } from "@/src/api/client";
import { ExtensionPairingCard } from "@/src/launcher/ExtensionPairingCard";
import {
  PROVIDERS,
  type ModelOption,
  type ProviderOption,
} from "@/src/llm/providers";
import { useTheme, type Theme } from "@/src/theme";
import type { LLMSettingsUpdate } from "@/src/api/types";

interface Props {
  apiBaseUrl: string;
}

type TestState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; latency: number }
  | { kind: "error"; message: string };

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "error"; message: string };

export function SettingsScreen({ apiBaseUrl }: Props) {
  const t = useTheme();
  const client = useMemo(() => searchClient(apiBaseUrl), [apiBaseUrl]);

  const [loading, setLoading] = useState(true);
  const [providerId, setProviderId] = useState<ProviderOption["id"]>(PROVIDERS[0].id);
  const provider = useMemo(
    () => PROVIDERS.find((p) => p.id === providerId)!,
    [providerId]
  );
  const [modelId, setModelId] = useState<string>(provider.models[0].id);
  const [maskedKey, setMaskedKey] = useState<string | null>(null);
  const [replaceMode, setReplaceMode] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [test, setTest] = useState<TestState>({ kind: "idle" });
  const [save, setSave] = useState<SaveState>({ kind: "idle" });

  // Load existing settings on mount.
  useEffect(() => {
    let cancelled = false;
    void client
      .getSettings()
      .then((s) => {
        if (cancelled) return;
        if (s) {
          const found =
            PROVIDERS.find((p) =>
              p.models.some((m) => m.id === s.primary_model)
            ) ?? PROVIDERS[0];
          setProviderId(found.id);
          setModelId(s.primary_model);
          setMaskedKey(s.primary_api_key_masked);
        }
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  // When provider changes (user-initiated), reset model to first option for that provider.
  const onPickProvider = (id: ProviderOption["id"]) => {
    if (id === providerId) return;
    const p = PROVIDERS.find((x) => x.id === id)!;
    setProviderId(id);
    setModelId(p.models[0].id);
    setTest({ kind: "idle" });
  };

  const onTest = async () => {
    setTest({ kind: "running" });
    try {
      const result = await client.testConnection({
        primary_model: modelId,
        primary_api_key:
          provider.needsKey && replaceMode && apiKey.length > 0 ? apiKey : null,
      });
      if (result.ok) {
        setTest({ kind: "ok", latency: result.latency_ms });
      } else {
        setTest({ kind: "error", message: result.error ?? "Unknown error" });
      }
    } catch (e) {
      setTest({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  };

  const onSave = async () => {
    setSave({ kind: "saving" });
    try {
      const body: LLMSettingsUpdate = { primary_model: modelId };
      if (replaceMode && apiKey.length > 0) {
        body.primary_api_key = apiKey;
      }
      const updated = await client.putSettings(body);
      setMaskedKey(updated.primary_api_key_masked);
      setReplaceMode(false);
      setApiKey("");
      setSave({ kind: "saved" });
    } catch (e) {
      setSave({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  };

  if (loading) {
    return (
      <View style={[styles.wrap, { backgroundColor: t.bg }]}>
        <Text style={{ color: t.textMuted }}>Loading settings…</Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={[styles.wrap, { backgroundColor: t.bg }]}>
      <Section title="Provider" theme={t}>
        {PROVIDERS.map((p) => (
          <Pressable
            key={p.id}
            accessibilityRole="radio"
            accessibilityState={{ selected: providerId === p.id }}
            onPress={() => onPickProvider(p.id)}
            style={[
              styles.row,
              {
                borderColor: t.border,
                backgroundColor: providerId === p.id ? t.surface : "transparent",
              },
            ]}
          >
            <Text style={{ color: t.text }}>{p.label}</Text>
          </Pressable>
        ))}
      </Section>

      <Section title="Model" theme={t}>
        {provider.models.map((m: ModelOption) => (
          <Pressable
            key={m.id}
            accessibilityRole="radio"
            accessibilityState={{ selected: modelId === m.id }}
            onPress={() => {
              setModelId(m.id);
              setTest({ kind: "idle" });
            }}
            style={[
              styles.row,
              {
                borderColor: t.border,
                backgroundColor: modelId === m.id ? t.surface : "transparent",
              },
            ]}
          >
            <Text style={{ color: t.text }}>
              {m.label}
              {m.free ? "  (free)" : ""}
            </Text>
          </Pressable>
        ))}
      </Section>

      {provider.needsKey ? (
        <Section title="API key" theme={t}>
          {!replaceMode ? (
            <View style={styles.keyRow}>
              <Text style={{ color: t.text, flex: 1 }}>{maskedKey ?? "(none)"}</Text>
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  setReplaceMode(true);
                  setTest({ kind: "idle" });
                }}
                style={[styles.btnSecondary, { borderColor: t.border }]}
              >
                <Text style={{ color: t.text }}>Replace</Text>
              </Pressable>
            </View>
          ) : (
            <View style={styles.keyRow}>
              <TextInput
                accessibilityLabel="API key"
                placeholder="sk-..."
                placeholderTextColor={t.textMuted}
                value={apiKey}
                onChangeText={(v) => {
                  setApiKey(v);
                  setTest({ kind: "idle" });
                }}
                secureTextEntry
                style={[
                  styles.input,
                  { color: t.text, borderColor: t.border, flex: 1 },
                ]}
              />
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  setReplaceMode(false);
                  setApiKey("");
                  setTest({ kind: "idle" });
                }}
                style={[styles.btnSecondary, { borderColor: t.border }]}
              >
                <Text style={{ color: t.text }}>Cancel</Text>
              </Pressable>
            </View>
          )}
        </Section>
      ) : null}

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          onPress={onTest}
          disabled={test.kind === "running"}
          style={[styles.btnSecondary, { borderColor: t.border }]}
        >
          <Text style={{ color: t.text }}>
            {test.kind === "running" ? "Testing…" : "Test connection"}
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onSave}
          disabled={save.kind === "saving"}
          style={[
            styles.btnPrimary,
            { backgroundColor: save.kind === "saving" ? t.textMuted : t.accent },
          ]}
        >
          <Text style={{ color: "#fff", fontWeight: "600" }}>
            {save.kind === "saving" ? "Saving…" : "Save"}
          </Text>
        </Pressable>
      </View>

      {test.kind === "ok" ? (
        <Text style={{ color: t.text, marginTop: 8 }}>
          Connection ok ({test.latency} ms)
        </Text>
      ) : null}
      {test.kind === "error" ? (
        <Text style={{ color: "#c00", marginTop: 8 }}>
          Connection error: {test.message}
        </Text>
      ) : null}
      {save.kind === "saved" ? (
        <Text style={{ color: t.ok, marginTop: 8 }}>Saved.</Text>
      ) : null}
      {save.kind === "error" ? (
        <Text style={{ color: "#c00", marginTop: 8 }}>
          Save failed: {save.message}
        </Text>
      ) : null}

      <View style={{ height: 8 }} />
      <ExtensionPairingCard apiBaseUrl={apiBaseUrl} client={client} />
    </ScrollView>
  );
}

function Section({
  title,
  children,
  theme,
}: {
  title: string;
  children: React.ReactNode;
  theme: Theme;
}) {
  return (
    <View style={styles.section}>
      <Text style={[styles.sectionTitle, { color: theme.text }]}>{title}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 24, gap: 16, minHeight: "100%" },
  section: { gap: 8 },
  sectionTitle: { fontWeight: "600", fontSize: 14 },
  row: { padding: 10, borderWidth: 1, borderRadius: 8 },
  input: { padding: 10, borderWidth: 1, borderRadius: 8 },
  keyRow: { flexDirection: "row", gap: 8, alignItems: "center" },
  actions: { flexDirection: "row", gap: 12, marginTop: 12 },
  btnSecondary: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderRadius: 8,
  },
  btnPrimary: { paddingHorizontal: 18, paddingVertical: 10, borderRadius: 8 },
});
