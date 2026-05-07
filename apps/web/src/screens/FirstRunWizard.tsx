import React, { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { searchClient } from "@/src/api/client";
import { PROVIDERS, type ModelOption, type ProviderOption } from "@/src/llm/providers";
import { useTheme, type Theme } from "@/src/theme";

interface Props {
  apiBaseUrl: string;
  onComplete: () => void;
}

type TestState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; latency: number }
  | { kind: "error"; message: string };

export function FirstRunWizard({ apiBaseUrl, onComplete }: Props) {
  const t = useTheme();
  const client = useMemo(() => searchClient(apiBaseUrl), [apiBaseUrl]);

  const [providerId, setProviderId] = useState<ProviderOption["id"]>(PROVIDERS[0].id);
  const provider = useMemo(
    () => PROVIDERS.find((p) => p.id === providerId)!,
    [providerId]
  );
  const [modelId, setModelId] = useState<string>(provider.models[0].id);
  const [apiKey, setApiKey] = useState<string>("");
  const [test, setTest] = useState<TestState>({ kind: "idle" });
  const [saving, setSaving] = useState(false);

  // Reset model when provider changes
  useEffect(() => {
    const p = PROVIDERS.find((x) => x.id === providerId)!;
    setModelId(p.models[0].id);
    setTest({ kind: "idle" });
  }, [providerId]);

  const onTest = async () => {
    setTest({ kind: "running" });
    try {
      const result = await client.testConnection({
        primary_model: modelId,
        primary_api_key: provider.needsKey ? apiKey : null,
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

  const onFinish = async () => {
    setSaving(true);
    try {
      await client.putSettings({
        primary_model: modelId,
        primary_api_key: provider.needsKey ? apiKey : null,
      });
      onComplete();
    } finally {
      setSaving(false);
    }
  };

  const canFinish = test.kind === "ok" || test.kind === "error"; /* allow skip */

  return (
    <ScrollView contentContainerStyle={[styles.wrap, { backgroundColor: t.bg }]}>
      <Text style={[styles.title, { color: t.text }]}>Welcome to RentWise</Text>
      <Text style={[styles.subtitle, { color: t.textMuted }]}>
        Pick an AI model to translate your searches.
      </Text>

      <Section title="Provider" theme={t}>
        {PROVIDERS.map((p) => (
          <Pressable
            key={p.id}
            accessibilityRole="radio"
            accessibilityState={{ selected: providerId === p.id }}
            onPress={() => setProviderId(p.id)}
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
            style={[styles.input, { color: t.text, borderColor: t.border }]}
          />
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
          onPress={onFinish}
          disabled={!canFinish || saving}
          style={[
            styles.btnPrimary,
            { backgroundColor: !canFinish || saving ? t.textMuted : t.accent },
          ]}
        >
          <Text style={{ color: "#fff", fontWeight: "600" }}>
            {test.kind === "error" ? "Skip and save anyway" : "Finish"}
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
  title: { fontSize: 24, fontWeight: "700" },
  subtitle: { fontSize: 14, marginBottom: 8 },
  section: { gap: 8 },
  sectionTitle: { fontWeight: "600", fontSize: 14 },
  row: { padding: 10, borderWidth: 1, borderRadius: 8 },
  input: { padding: 10, borderWidth: 1, borderRadius: 8 },
  actions: { flexDirection: "row", gap: 12, marginTop: 12 },
  btnSecondary: { paddingHorizontal: 14, paddingVertical: 10, borderWidth: 1, borderRadius: 8 },
  btnPrimary: { paddingHorizontal: 18, paddingVertical: 10, borderRadius: 8 },
});
