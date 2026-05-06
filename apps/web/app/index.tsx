import Constants from "expo-constants";
import { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";

const API_BASE_URL =
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  "http://localhost:8000";

type ApiHealth = {
  status: string;
};

type LlmHealth = {
  configured: boolean;
  primary_model: string;
  fallback_model: string | null;
};

export default function HomeScreen() {
  const [apiHealth, setApiHealth] = useState<ApiHealth | null>(null);
  const [llmHealth, setLlmHealth] = useState<LlmHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const [apiRes, llmRes] = await Promise.all([
          fetch(`${API_BASE_URL}/health`),
          fetch(`${API_BASE_URL}/health/llm`),
        ]);
        if (cancelled) return;
        setApiHealth(await apiRes.json());
        setLlmHealth(await llmRes.json());
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    check();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>RentWise</Text>
      <Text style={styles.subtitle}>
        Natural-language rental search across every Vancouver platform.
      </Text>
      <Text style={styles.subtitleKr}>
        밴쿠버의 모든 임대 플랫폼을 자연어로 한 번에 검색
      </Text>

      <View style={styles.statusCard}>
        <Text style={styles.statusHeading}>System status</Text>

        {loading ? (
          <ActivityIndicator color="#0ea5e9" />
        ) : error ? (
          <Text style={styles.error}>API unreachable: {error}</Text>
        ) : (
          <>
            <StatusRow
              label="API"
              value={apiHealth?.status === "ok" ? "online" : "offline"}
              ok={apiHealth?.status === "ok"}
            />
            <StatusRow
              label="LLM key"
              value={llmHealth?.configured ? "configured" : "not configured"}
              ok={!!llmHealth?.configured}
            />
            <StatusRow
              label="LLM model"
              value={llmHealth?.primary_model ?? "—"}
              ok
            />
          </>
        )}
      </View>

      <View style={styles.phaseCard}>
        <Text style={styles.phaseHeading}>Phase 0 — Foundations</Text>
        <Text style={styles.phaseBody}>
          The skeleton is up. Search and LLM features arrive in Phase 1 and 2.
          See <Text style={styles.code}>docs/roadmap.md</Text>.
        </Text>
      </View>
    </ScrollView>
  );
}

function StatusRow({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <View style={styles.statusRow}>
      <Text style={styles.statusLabel}>{label}</Text>
      <Text style={[styles.statusValue, ok ? styles.ok : styles.warn]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#020617" },
  content: { padding: 24, gap: 24, maxWidth: 640, width: "100%", alignSelf: "center" },
  title: { fontSize: 40, fontWeight: "700", color: "#f8fafc", marginTop: 24 },
  subtitle: { fontSize: 16, color: "#cbd5e1", lineHeight: 24 },
  subtitleKr: { fontSize: 14, color: "#94a3b8", lineHeight: 22 },
  statusCard: {
    backgroundColor: "#0f172a",
    borderRadius: 12,
    padding: 20,
    gap: 12,
    borderWidth: 1,
    borderColor: "#1e293b",
  },
  statusHeading: {
    fontSize: 14,
    fontWeight: "600",
    color: "#94a3b8",
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  statusRow: { flexDirection: "row", justifyContent: "space-between" },
  statusLabel: { color: "#cbd5e1" },
  statusValue: { fontFamily: "monospace" },
  ok: { color: "#22c55e" },
  warn: { color: "#f59e0b" },
  error: { color: "#ef4444" },
  phaseCard: {
    backgroundColor: "#0f172a",
    borderRadius: 12,
    padding: 20,
    gap: 8,
    borderLeftWidth: 4,
    borderLeftColor: "#0ea5e9",
  },
  phaseHeading: { fontSize: 14, fontWeight: "600", color: "#0ea5e9" },
  phaseBody: { color: "#cbd5e1", lineHeight: 22 },
  code: {
    fontFamily: "monospace",
    backgroundColor: "#1e293b",
    paddingHorizontal: 6,
    borderRadius: 4,
  },
});
