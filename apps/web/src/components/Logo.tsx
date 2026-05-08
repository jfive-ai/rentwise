import React from "react";
import { Image, Platform, Text, View } from "react-native";

const BRAND_RED = "#811B02";
const BRAND_GREEN = "#A3E635";

const MARK_ASPECT = 462 / 482;

const MARK_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 462 482" fill="none"><g transform="translate(4 7)"><path d="M414 240.668V191.252C414 181.335 409.67 171.912 402.145 165.453L236.424 23.201C223.673 12.256 204.839 12.2676 192.102 23.2284L26.8229 165.455C19.3171 171.913 15 181.324 15 191.226V381.168C15 399.946 30.2223 415.168 49 415.168H239.157" stroke="${BRAND_GREEN}" stroke-width="30" stroke-linejoin="round"/></g><rect x="125" y="198" width="37" height="37" fill="${BRAND_RED}"/><rect x="182" y="198" width="37" height="37" fill="${BRAND_RED}"/><rect x="125" y="255" width="37" height="37" fill="${BRAND_RED}"/><rect x="182" y="255" width="37" height="37" fill="${BRAND_RED}"/><circle cx="354" cy="363" r="77" stroke="${BRAND_RED}" stroke-width="24"/><line x1="408.5" y1="428" x2="446" y2="465.5" stroke="${BRAND_RED}" stroke-width="24" stroke-linecap="round"/></svg>`;

// react-native-web's Image component drops some data URIs when applied as a
// CSS background-image. Use a plain <img> on web for reliable SVG rendering;
// fall back to <Image> on native (where this app's not yet used).
const MARK_URI =
  Platform.OS === "web"
    ? `data:image/svg+xml;utf8,${encodeURIComponent(MARK_SVG)}`
    : `data:image/svg+xml;base64,${
        typeof btoa !== "undefined"
          ? btoa(MARK_SVG)
          : Buffer.from(MARK_SVG, "utf-8").toString("base64")
      }`;

interface LogoMarkProps {
  size?: number;
}

export function LogoMark({ size = 28 }: LogoMarkProps) {
  const w = size * MARK_ASPECT;
  if (Platform.OS === "web") {
    return React.createElement("img", {
      src: MARK_URI,
      alt: "",
      "aria-hidden": true,
      style: { width: w, height: size, display: "block" },
    });
  }
  return (
    <Image
      source={{ uri: MARK_URI }}
      accessibilityLabel="RentWise logo"
      style={{ width: w, height: size }}
    />
  );
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
