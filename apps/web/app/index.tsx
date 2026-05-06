import Constants from "expo-constants";
import { SearchScreen } from "@/src/screens/SearchScreen";

const API_BASE_URL =
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  "http://localhost:8000";

export default function HomeScreen() {
  return <SearchScreen apiBaseUrl={API_BASE_URL} />;
}
