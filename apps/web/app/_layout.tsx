import { Stack } from "expo-router";
import { QueryProvider } from "@/src/state/QueryProvider";

export default function RootLayout() {
  return (
    <QueryProvider>
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: "#0f172a" },
          headerTintColor: "#f8fafc",
          headerTitleStyle: { fontWeight: "600" },
        }}
      >
        <Stack.Screen name="index" options={{ title: "RentWise" }} />
      </Stack>
    </QueryProvider>
  );
}
