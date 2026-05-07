import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useQuery } from "@/src/state/QueryProvider";
import { useTheme, type Theme } from "@/src/theme";

export function ModeToggle() {
  const t = useTheme();
  const { mode, setMode } = useQuery();
  return (
    <View style={[styles.wrap, { borderColor: t.border }]}>
      <Pill
        label="Natural language"
        active={mode === "nl"}
        onPress={() => setMode("nl")}
        t={t}
      />
      <Pill
        label="Filters"
        active={mode === "filters"}
        onPress={() => setMode("filters")}
        t={t}
      />
    </View>
  );
}

function Pill({
  label,
  active,
  onPress,
  t,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  t: Theme;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      accessibilityLabel={label}
      onPress={onPress}
      style={[
        styles.pill,
        { backgroundColor: active ? t.accent : "transparent" },
      ]}
    >
      <Text
        style={{
          color: active ? "#fff" : t.text,
          fontSize: 13,
          fontWeight: "600",
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    borderWidth: 1,
    borderRadius: 999,
    padding: 2,
    alignSelf: "flex-start",
  },
  pill: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 999,
  },
});
