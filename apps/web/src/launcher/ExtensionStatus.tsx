import React, { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import type { ApiClient } from "@/src/api/client";
import { useTheme } from "@/src/theme";

type Status =
  | { kind: "loading" }
  | { kind: "paired"; tokenPreview: string }
  | { kind: "unreachable"; message: string };

interface Props {
  client: ApiClient;
}

/** Probes `/capture/pair` and shows whether the API is reachable. */
export function ExtensionStatus({ client }: Props) {
  const t = useTheme();
  const [status, setStatus] = useState<Status>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const pair = await client.getCapturePair();
        if (cancelled) return;
        setStatus({ kind: "paired", tokenPreview: previewToken(pair.token) });
      } catch (e) {
        if (cancelled) return;
        setStatus({
          kind: "unreachable",
          message: e instanceof Error ? e.message : String(e),
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client]);

  if (status.kind === "loading") {
    return <Text style={{ color: t.textMuted }}>Checking extension API…</Text>;
  }
  if (status.kind === "unreachable") {
    return (
      <View style={[styles.row, { borderColor: t.border, backgroundColor: t.surface }]}>
        <Text style={{ color: "#a30" }}>⚠️ Capture API unreachable</Text>
        <Text style={{ color: t.textMuted, fontSize: 12, marginTop: 2 }}>{status.message}</Text>
      </View>
    );
  }
  return (
    <View style={[styles.row, { borderColor: t.border, backgroundColor: t.surface }]}>
      <Text style={{ color: "#0a7" }}>✅ Capture API ready</Text>
      <Text style={{ color: t.textMuted, fontSize: 12, marginTop: 2 }}>
        Token: {status.tokenPreview}
      </Text>
    </View>
  );
}

function previewToken(token: string): string {
  if (token.length <= 8) return token;
  return `${token.slice(0, 4)}…${token.slice(-4)}`;
}

const styles = StyleSheet.create({
  row: { padding: 10, borderWidth: 1, borderRadius: 8 },
});
