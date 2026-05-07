import React, { useEffect, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
import type { ApiClient } from "@/src/api/client";
import { useTheme } from "@/src/theme";

interface Props {
  apiBaseUrl: string;
  client: ApiClient;
}

type State =
  | { kind: "loading" }
  | { kind: "loaded"; token: string; serverUrl: string }
  | { kind: "error"; message: string };

/**
 * Settings → Extension card. Shows the pairing token + server URL the
 * user pastes into the extension's options page; lets them rotate the
 * token (calls POST /capture/pair/rotate, which returns the new value
 * directly per spec § 6.2).
 */
export function ExtensionPairingCard({ apiBaseUrl, client }: Props) {
  const t = useTheme();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [revealed, setRevealed] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [copyHint, setCopyHint] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const pair = await client.getCapturePair();
        if (cancelled) return;
        setState({ kind: "loaded", token: pair.token, serverUrl: pair.server_url });
      } catch (e) {
        if (cancelled) return;
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : String(e),
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client]);

  const onRotate = async () => {
    setRotating(true);
    try {
      const pair = await client.rotateCapturePair();
      setState({ kind: "loaded", token: pair.token, serverUrl: pair.server_url });
      setRevealed(true);
    } catch (e) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setRotating(false);
    }
  };

  const onCopy = async (value: string, label: string) => {
    if (Platform.OS !== "web" || typeof navigator === "undefined" || !navigator.clipboard) {
      setCopyHint(`${label}: copy is only available in the web app`);
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setCopyHint(`${label} copied`);
    } catch {
      setCopyHint(`${label}: copy failed`);
    }
  };

  return (
    <View style={[styles.card, { borderColor: t.border, backgroundColor: t.surface }]}>
      <Text style={[styles.title, { color: t.text }]}>Browser extension pairing</Text>
      <Text style={[styles.sub, { color: t.textMuted }]}>
        Paste these values into the RentWise Capture extension&apos;s options page so it
        can post captures to your local API.
      </Text>

      {state.kind === "loading" && (
        <Text style={{ color: t.textMuted, marginTop: 8 }}>Loading pairing…</Text>
      )}
      {state.kind === "error" && (
        <Text style={{ color: "#c00", marginTop: 8 }}>
          Couldn&apos;t load pairing: {state.message}
        </Text>
      )}
      {state.kind === "loaded" && (
        <View style={styles.fields}>
          <FieldRow
            label="API URL"
            value={state.serverUrl}
            displayValue={state.serverUrl}
            onCopy={() => void onCopy(state.serverUrl, "API URL")}
          />
          <FieldRow
            label="Pairing token"
            value={state.token}
            displayValue={revealed ? state.token : maskToken(state.token)}
            onCopy={() => void onCopy(state.token, "Token")}
            extra={
              <Pressable
                accessibilityRole="button"
                onPress={() => setRevealed((v) => !v)}
                style={[styles.btnSm, { borderColor: t.border }]}
              >
                <Text style={{ color: t.text }}>{revealed ? "Hide" : "Reveal"}</Text>
              </Pressable>
            }
          />
        </View>
      )}

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          onPress={() => void onRotate()}
          disabled={rotating || state.kind !== "loaded"}
          style={[styles.btnSecondary, { borderColor: t.border }]}
        >
          <Text style={{ color: t.text }}>
            {rotating ? "Rotating…" : "Rotate token"}
          </Text>
        </Pressable>
      </View>

      {copyHint && (
        <Text style={{ color: t.textMuted, marginTop: 8, fontSize: 12 }}>{copyHint}</Text>
      )}

      <Text style={[styles.sub, { color: t.textMuted, marginTop: 12 }]}>
        Tip: keep the API at <Text style={{ fontFamily: "Menlo" }}>{apiBaseUrl}</Text> if
        you&apos;re running the default local stack.
      </Text>
    </View>
  );
}

function FieldRow({
  label,
  displayValue,
  onCopy,
  extra,
}: {
  label: string;
  value: string;
  displayValue: string;
  onCopy: () => void;
  extra?: React.ReactNode;
}) {
  const t = useTheme();
  return (
    <View style={{ gap: 4 }}>
      <Text style={[styles.fieldLabel, { color: t.textMuted }]}>{label}</Text>
      <View style={styles.fieldRow}>
        <Text
          selectable
          style={[
            styles.fieldValue,
            { color: t.text, borderColor: t.border },
          ]}
        >
          {displayValue}
        </Text>
        <Pressable
          accessibilityRole="button"
          onPress={onCopy}
          style={[styles.btnSm, { borderColor: t.border }]}
        >
          <Text style={{ color: t.text }}>Copy</Text>
        </Pressable>
        {extra}
      </View>
    </View>
  );
}

function maskToken(token: string): string {
  if (token.length <= 8) return "••••••••";
  return `${token.slice(0, 4)}${"•".repeat(Math.max(token.length - 8, 4))}${token.slice(-4)}`;
}

const styles = StyleSheet.create({
  card: { padding: 16, borderWidth: 1, borderRadius: 8, gap: 8 },
  title: { fontWeight: "600", fontSize: 14 },
  sub: { fontSize: 12 },
  fields: { gap: 12, marginTop: 8 },
  fieldLabel: { fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 },
  fieldRow: { flexDirection: "row", gap: 8, alignItems: "center" },
  fieldValue: {
    flex: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderRadius: 6,
    fontFamily: "Menlo",
  },
  btnSm: { paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderRadius: 6 },
  btnSecondary: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderRadius: 8,
  },
  actions: { flexDirection: "row", gap: 8, marginTop: 12 },
});
