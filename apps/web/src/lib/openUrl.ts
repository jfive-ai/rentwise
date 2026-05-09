import * as Linking from "expo-linking";
import { Platform } from "react-native";

/**
 * Open `url` in the user's preferred way for the current platform:
 * - Web: a new tab with `noopener,noreferrer` so RentWise keeps its in-page
 *   state (selected listing, scroll, map viewport, NL history) when the
 *   user wants to inspect the source.
 * - Native (iOS / macOS / Tauri webview): defer to `Linking.openURL` so
 *   the OS picks the appropriate handler.
 *
 * Returns void; failures are swallowed to match the existing call sites.
 */
export function openExternalUrl(url: string): void {
  if (Platform.OS === "web" && typeof window !== "undefined") {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  void Linking.openURL(url);
}
