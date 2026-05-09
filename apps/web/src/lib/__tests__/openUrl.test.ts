import { Platform } from "react-native";
import * as Linking from "expo-linking";
import { openExternalUrl } from "@/src/lib/openUrl";

jest.mock("expo-linking", () => ({ openURL: jest.fn().mockResolvedValue(undefined) }));

describe("openExternalUrl", () => {
  const realPlatformOS = Platform.OS;
  const realWindowOpen = global.window?.open;

  afterEach(() => {
    // Restore so other suites that share Platform.OS aren't affected.
    Object.defineProperty(Platform, "OS", { configurable: true, value: realPlatformOS });
    if (global.window) {
      global.window.open = realWindowOpen as typeof global.window.open;
    }
    jest.clearAllMocks();
  });

  it("opens a new tab on web with noopener,noreferrer", () => {
    Object.defineProperty(Platform, "OS", { configurable: true, value: "web" });
    const winOpen = jest.fn();
    global.window.open = winOpen as unknown as typeof global.window.open;
    openExternalUrl("https://example.com/listing/1");
    expect(winOpen).toHaveBeenCalledWith(
      "https://example.com/listing/1",
      "_blank",
      "noopener,noreferrer",
    );
    expect((Linking.openURL as jest.Mock)).not.toHaveBeenCalled();
  });

  it("falls back to Linking.openURL on native", () => {
    Object.defineProperty(Platform, "OS", { configurable: true, value: "ios" });
    openExternalUrl("https://example.com/listing/2");
    expect((Linking.openURL as jest.Mock)).toHaveBeenCalledWith(
      "https://example.com/listing/2",
    );
  });
});
