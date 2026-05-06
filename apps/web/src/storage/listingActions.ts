import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "rentwise.listingActions.v1";

export type ActionFlag = "saved" | "hidden" | "contacted";
export type ListingActions = Partial<Record<ActionFlag, boolean>>;
export type ListingActionMap = Record<string, ListingActions>;

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

export async function loadActions(): Promise<ListingActionMap> {
  const raw = await backend().getItem(KEY);
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as ListingActionMap;
    }
    return {};
  } catch {
    return {};
  }
}

export async function setAction(
  listingId: string,
  flag: ActionFlag,
  value: boolean
): Promise<ListingActionMap> {
  const map = await loadActions();
  const current: ListingActions = { ...(map[listingId] ?? {}) };
  if (value) {
    current[flag] = true;
  } else {
    delete current[flag];
  }
  if (Object.keys(current).length === 0) {
    delete map[listingId];
  } else {
    map[listingId] = current;
  }
  await backend().setItem(KEY, JSON.stringify(map));
  return map;
}

export async function clearActions(): Promise<void> {
  await backend().removeItem(KEY);
}
