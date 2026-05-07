import Constants from "expo-constants";
import { SettingsScreen } from "@/src/screens/SettingsScreen";

const API_BASE_URL =
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  "http://localhost:8000";

export default function SettingsRoute() {
  return <SettingsScreen apiBaseUrl={API_BASE_URL} />;
}
