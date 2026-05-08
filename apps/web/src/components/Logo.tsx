import React from "react";
import { Platform, Text, View } from "react-native";

const BRAND_RED = "#811B02";
const BRAND_GREEN = "#A3E635";

const MARK_ASPECT = 462 / 482;
const MARK_SRC = "/logo-mark.svg";

interface LogoMarkProps {
  size?: number;
}

export function LogoMark({ size = 28 }: LogoMarkProps) {
  const w = size * MARK_ASPECT;
  if (Platform.OS !== "web") {
    // Native rendering of the mark is not yet implemented — render a sized
    // placeholder so the lockup layout doesn't shift. Add react-native-svg
    // (or an Image asset) when shipping to iOS/macOS/Android.
    return <View style={{ width: w, height: size }} />;
  }
  return React.createElement("img", {
    src: MARK_SRC,
    alt: "",
    "aria-hidden": true,
    style: { width: w, height: size, display: "block" },
  });
}

interface LogoLockupProps {
  size?: number;
  gap?: number;
}

export function LogoLockup({ size = 26, gap = 8 }: LogoLockupProps) {
  return (
    <View
      accessibilityRole="header"
      accessibilityLabel="RentWise"
      style={{ flexDirection: "row", alignItems: "center", gap }}
    >
      <LogoMark size={size} />
      <Text
        style={{
          fontSize: size * 0.78,
          fontWeight: "700",
          letterSpacing: -0.3,
        }}
      >
        <Text style={{ color: BRAND_RED }}>Rent</Text>
        <Text style={{ color: BRAND_GREEN }}> Wise</Text>
      </Text>
    </View>
  );
}
