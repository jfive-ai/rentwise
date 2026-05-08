import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "rentwise.nlSearchHistory.v1";
export const MAX_ENTRIES = 10;

interface StorageBackend {
  getItem(k: string): Promise<string | null>;
  setItem(k: string, v: string): Promise<void>;
  removeItem(k: string): Promise<void>;
}

function backend(): StorageBackend {
  if (Platform.OS === "web") {
    return {
      async getItem(k) {
        return window.localStorage.getItem(k);
      },
      async setItem(k, v) {
        window.localStorage.setItem(k, v);
      },
      async removeItem(k) {
        window.localStorage.removeItem(k);
      },
    };
  }
  return {
    async getItem(k) {
      return AsyncStorage.getItem(k);
    },
    async setItem(k, v) {
      await AsyncStorage.setItem(k, v);
    },
    async removeItem(k) {
      await AsyncStorage.removeItem(k);
    },
  };
}

function sanitize(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const out: string[] = [];
  for (const v of raw) {
    if (typeof v === "string") {
      const trimmed = v.trim();
      if (trimmed) out.push(trimmed);
    }
  }
  return out.slice(0, MAX_ENTRIES);
}

export async function loadHistory(): Promise<string[]> {
  const raw = await backend().getItem(KEY);
  if (!raw) return [];
  try {
    return sanitize(JSON.parse(raw));
  } catch {
    return [];
  }
}

/**
 * Add an entry to the history. Most-recent-first; duplicates promote to top
 * (case-sensitive after trim) rather than repeating; capped at MAX_ENTRIES.
 * Returns the updated list.
 */
export async function addEntry(text: string): Promise<string[]> {
  const trimmed = text.trim();
  if (!trimmed) return loadHistory();
  const current = await loadHistory();
  const without = current.filter((entry) => entry !== trimmed);
  const next = [trimmed, ...without].slice(0, MAX_ENTRIES);
  await backend().setItem(KEY, JSON.stringify(next));
  return next;
}

export async function removeEntry(text: string): Promise<string[]> {
  const current = await loadHistory();
  const next = current.filter((entry) => entry !== text);
  if (next.length === current.length) return current;
  await backend().setItem(KEY, JSON.stringify(next));
  return next;
}

export async function clearHistory(): Promise<void> {
  await backend().removeItem(KEY);
}
