import { useColorScheme } from "react-native";

export interface Theme {
  bg: string;
  surface: string;
  surfaceAlt: string;
  border: string;
  text: string;
  textMuted: string;
  accent: string;
  ok: string;
  warn: string;
  error: string;
  disabled: string;
}

export const lightTheme: Theme = {
  bg: "#ffffff",
  surface: "#f8fafc",
  surfaceAlt: "#e2e8f0",
  border: "#cbd5e1",
  text: "#0f172a",
  textMuted: "#475569",
  accent: "#0ea5e9",
  ok: "#16a34a",
  warn: "#d97706",
  error: "#dc2626",
  disabled: "#94a3b8",
};

export const darkTheme: Theme = {
  bg: "#020617",
  surface: "#0f172a",
  surfaceAlt: "#1e293b",
  border: "#334155",
  text: "#f8fafc",
  textMuted: "#cbd5e1",
  accent: "#38bdf8",
  ok: "#22c55e",
  warn: "#f59e0b",
  error: "#ef4444",
  disabled: "#64748b",
};

export function useTheme(): Theme {
  const scheme = useColorScheme();
  return scheme === "light" ? lightTheme : darkTheme;
}
