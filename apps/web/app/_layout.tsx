import { Link, Stack } from "expo-router";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Platform, Text, View } from "react-native";
import Constants from "expo-constants";
import { QueryProvider } from "@/src/state/QueryProvider";
import { FirstRunWizard } from "@/src/screens/FirstRunWizard";
import { searchClient } from "@/src/api/client";

const API_BASE_URL =
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  "http://localhost:8000";

const WIZARD_FLAG_KEY = "rentwise.wizardCompleted";

function readFlag(): boolean {
  if (Platform.OS !== "web") return false;
  try {
    return window.localStorage.getItem(WIZARD_FLAG_KEY) === "v1";
  } catch {
    return false;
  }
}

function writeFlag() {
  if (Platform.OS !== "web") return;
  try {
    window.localStorage.setItem(WIZARD_FLAG_KEY, "v1");
  } catch {
    /* noop */
  }
}

export default function RootLayout() {
  // "checking" until we know whether to show the wizard.
  const [phase, setPhase] = useState<"checking" | "wizard" | "ready">(() =>
    readFlag() ? "ready" : "checking"
  );

  useEffect(() => {
    if (phase !== "checking") return;
    let cancelled = false;
    void searchClient(API_BASE_URL)
      .getSettings()
      .then((s) => {
        if (cancelled) return;
        if (s) {
          writeFlag();
          setPhase("ready");
        } else {
          setPhase("wizard");
        }
      })
      .catch(() => {
        // API unreachable — fail open into the app; the user can configure later.
        if (!cancelled) setPhase("ready");
      });
    return () => {
      cancelled = true;
    };
  }, [phase]);

  if (phase === "checking") {
    return (
      <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
        <ActivityIndicator />
      </View>
    );
  }

  if (phase === "wizard") {
    return (
      <FirstRunWizard
        apiBaseUrl={API_BASE_URL}
        onComplete={() => {
          writeFlag();
          setPhase("ready");
        }}
      />
    );
  }

  return (
    <QueryProvider>
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: "#0f172a" },
          headerTintColor: "#f8fafc",
          headerTitleStyle: { fontWeight: "600" },
        }}
      >
        <Stack.Screen
          name="index"
          options={{
            title: "RentWise",
            headerRight: () => (
              <Link href="/settings" accessibilityLabel="Open settings">
                <Text style={{ color: "#f8fafc", fontSize: 18, paddingHorizontal: 12 }}>
                  ⚙
                </Text>
              </Link>
            ),
          }}
        />
        <Stack.Screen name="settings" options={{ title: "Settings" }} />
      </Stack>
    </QueryProvider>
  );
}
