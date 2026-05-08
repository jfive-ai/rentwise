/**
 * Phase 5 PR-C: enable / disable browser web-push notifications.
 *
 * On enable:
 *   1. Probe `/notifications/web-push/public-key`. 503 → server hasn't
 *      configured VAPID; show a friendly hint instead of an error.
 *   2. Request `Notification.requestPermission()`.
 *   3. Register `/sw.js` and call `pushManager.subscribe(...)` with
 *      the VAPID public key.
 *   4. POST the subscription JSON (+ user's alert_email) to
 *      `/notifications/web-push/subscribe`.
 *
 * On disable: unsubscribe locally, then DELETE the row from the server.
 *
 * The component is web-only — on iOS / macOS it renders a placeholder.
 * Mobile push is Phase 8 territory.
 */

import React, { useEffect, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import type { ApiClient } from "@/src/api/client";
import { useTheme } from "@/src/theme";

interface Props {
  client: ApiClient;
}

const STORAGE_KEY = "rentwise.webPushSubscriptionId";

type State =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "unsupported" } // browser doesn't speak the API
  | { kind: "unconfigured" } // server hasn't set VAPID keys
  | { kind: "off" }
  | { kind: "on"; subscriptionId: number }
  | { kind: "error"; message: string };

export function BrowserNotificationsCard({ client }: Props) {
  const t = useTheme();
  const [state, setState] = useState<State>({ kind: "checking" });
  const [email, setEmail] = useState("");

  useEffect(() => {
    void initialCheck(client).then(setState);
  }, [client]);

  const onEnable = async () => {
    setState({ kind: "checking" });
    try {
      const id = await enableWebPush(client, email.trim() || null);
      setState({ kind: "on", subscriptionId: id });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setState({ kind: "error", message: msg });
    }
  };

  const onDisable = async () => {
    if (state.kind !== "on") return;
    setState({ kind: "checking" });
    try {
      await disableWebPush(client, state.subscriptionId);
      setState({ kind: "off" });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setState({ kind: "error", message: msg });
    }
  };

  return (
    <View style={[styles.card, { borderColor: t.border, backgroundColor: t.surface }]}>
      <Text style={[styles.title, { color: t.text }]}>Browser notifications</Text>
      <Text style={[styles.sub, { color: t.textMuted }]}>
        Push notifications fire alongside email when a saved search has new
        matches. Web-only for now.
      </Text>

      {state.kind === "unsupported" && (
        <Text style={[styles.note, { color: t.textMuted }]}>
          This browser doesn&apos;t support web push. Try Chrome, Edge, or
          Firefox on desktop.
        </Text>
      )}

      {state.kind === "unconfigured" && (
        <Text style={[styles.note, { color: t.textMuted }]}>
          The server isn&apos;t configured for web push yet.
          See <Text style={{ fontFamily: "Menlo" }}>docs/roadmap.md</Text>{" "}
          Phase 5 PR-C and run <Text style={{ fontFamily: "Menlo" }}>scripts/gen_vapid.py</Text>.
        </Text>
      )}

      {state.kind === "off" && (
        <>
          <Text style={[styles.label, { color: t.textMuted }]}>
            Email (must match the saved search&apos;s alert email to receive
            pushes for it)
          </Text>
          <TextInput
            accessibilityLabel="Push alert email"
            placeholder="you@example.com"
            placeholderTextColor={t.textMuted}
            keyboardType="email-address"
            autoCapitalize="none"
            value={email}
            onChangeText={setEmail}
            style={[styles.input, { color: t.text, borderColor: t.border }]}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Enable browser notifications"
            onPress={() => void onEnable()}
            style={[styles.btn, { borderColor: t.border, backgroundColor: t.accent }]}
          >
            <Text style={{ color: "#fff" }}>Enable</Text>
          </Pressable>
        </>
      )}

      {state.kind === "on" && (
        <>
          <Text style={{ color: "#0a7" }}>✓ Browser notifications enabled.</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Disable browser notifications"
            onPress={() => void onDisable()}
            style={[styles.btn, { borderColor: t.border }]}
          >
            <Text style={{ color: t.text }}>Disable</Text>
          </Pressable>
        </>
      )}

      {state.kind === "error" && (
        <Text style={{ color: "#a30" }}>Couldn&apos;t set up: {state.message}</Text>
      )}

      {state.kind === "checking" && (
        <Text style={{ color: t.textMuted }}>Checking…</Text>
      )}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Helpers — exported for unit testing.
// ---------------------------------------------------------------------------

export async function initialCheck(client: ApiClient): Promise<State> {
  if (Platform.OS !== "web") return { kind: "unsupported" };
  if (
    typeof window === "undefined"
    || !("serviceWorker" in navigator)
    || !("PushManager" in window)
    || typeof Notification === "undefined"
  ) {
    return { kind: "unsupported" };
  }
  const key = await client.getWebPushPublicKey();
  if (key === null) return { kind: "unconfigured" };

  // Recover state across reloads via localStorage.
  if (typeof localStorage !== "undefined") {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null) {
      const id = Number.parseInt(stored, 10);
      if (Number.isFinite(id)) return { kind: "on", subscriptionId: id };
    }
  }
  return { kind: "off" };
}

export async function enableWebPush(
  client: ApiClient,
  alertEmail: string | null,
): Promise<number> {
  const keyResp = await client.getWebPushPublicKey();
  if (keyResp === null) throw new Error("server not configured for web push");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("notification permission denied");
  }

  const reg = await navigator.serviceWorker.register("/sw.js");
  // applicationServerKey takes a BufferSource at runtime, but the TS
  // lib types it narrowly enough that Uint8Array<ArrayBufferLike>
  // (the result of `urlBase64ToUint8Array`) doesn't fit. Cast at the
  // boundary — the runtime accepts the Uint8Array directly.
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(
      keyResp.public_key,
    ) as unknown as BufferSource,
  });

  const json = sub.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    throw new Error("subscription missing required fields");
  }
  const saved = await client.subscribeWebPush({
    endpoint: json.endpoint,
    keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
    alert_email: alertEmail,
  });
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(STORAGE_KEY, String(saved.id));
  }
  return saved.id;
}

export async function disableWebPush(
  client: ApiClient,
  subscriptionId: number,
): Promise<void> {
  // Best-effort browser-side unsubscribe; server-side delete is what
  // actually stops new dispatches.
  try {
    const reg = await navigator.serviceWorker.getRegistration("/sw.js");
    const sub = await reg?.pushManager.getSubscription();
    if (sub) await sub.unsubscribe();
  } catch {
    // Ignore — server-side delete still happens.
  }
  await client.unsubscribeWebPush(subscriptionId);
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem(STORAGE_KEY);
  }
}

/** VAPID public key arrives base64-url-encoded; PushManager wants Uint8Array. */
export function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const normalized = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(normalized);
  const buf = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) buf[i] = raw.charCodeAt(i);
  return buf;
}

const styles = StyleSheet.create({
  card: { padding: 16, borderWidth: 1, borderRadius: 8, gap: 8 },
  title: { fontSize: 14, fontWeight: "600" },
  sub: { fontSize: 12 },
  note: { fontSize: 12 },
  label: { fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 },
  input: { borderWidth: 1, borderRadius: 6, padding: 8 },
  btn: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderRadius: 6,
    alignSelf: "flex-start",
  },
});
