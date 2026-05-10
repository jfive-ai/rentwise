/** @jest-environment jsdom */
import { Platform } from "react-native";
import type { ApiClient } from "@/src/api/client";
import {
  initialCheck,
  urlBase64ToUint8Array,
} from "@/src/components/BrowserNotificationsCard";

beforeAll(() => {
  // The web push integration is web-only — pretend we're on web for the
  // jest run.
  (Platform as { OS: string }).OS = "web";
});

function makeClient(overrides: Partial<ApiClient>): ApiClient {
  const base: ApiClient = {
    search: jest.fn(),
    searchStream: jest.fn(),
    translateQuery: jest.fn(),
    getSettings: jest.fn(),
    putSettings: jest.fn(),
    testConnection: jest.fn(),
    saveSearch: jest.fn(),
    listSavedSearches: jest.fn(),
    deleteSavedSearch: jest.fn(),
    getWebPushPublicKey: jest.fn(),
    subscribeWebPush: jest.fn(),
    unsubscribeWebPush: jest.fn(),
  };
  return { ...base, ...overrides };
}

describe("urlBase64ToUint8Array", () => {
  it("decodes a known url-safe base64 value to the expected bytes", () => {
    // 0x00 0x10 0xff 0xfe → "ABD//g==" but url-safe is "ABD__g".
    const out = urlBase64ToUint8Array("ABD__g");
    expect(Array.from(out)).toEqual([0x00, 0x10, 0xff, 0xfe]);
  });

  it("handles missing padding", () => {
    const out = urlBase64ToUint8Array("Zg"); // 'f' = 0x66
    expect(Array.from(out)).toEqual([0x66]);
  });
});

describe("initialCheck", () => {
  const originalServiceWorker = navigator.serviceWorker;
  const originalPushManager = (window as { PushManager?: unknown }).PushManager;
  const originalNotification = (globalThis as { Notification?: unknown }).Notification;

  function setSupportedBrowser(supported: boolean) {
    if (supported) {
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: { register: jest.fn(), getRegistration: jest.fn() },
      });
      (window as { PushManager?: unknown }).PushManager = function () {};
      (globalThis as { Notification?: unknown }).Notification =
        function () {} as unknown;
    } else {
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: undefined,
      });
      delete (window as { PushManager?: unknown }).PushManager;
      delete (globalThis as { Notification?: unknown }).Notification;
    }
  }

  afterEach(() => {
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: originalServiceWorker,
    });
    if (originalPushManager !== undefined) {
      (window as { PushManager?: unknown }).PushManager = originalPushManager;
    } else {
      delete (window as { PushManager?: unknown }).PushManager;
    }
    if (originalNotification !== undefined) {
      (globalThis as { Notification?: unknown }).Notification =
        originalNotification;
    } else {
      delete (globalThis as { Notification?: unknown }).Notification;
    }
    window.localStorage.clear();
  });

  it("reports unsupported when the browser lacks the API", async () => {
    setSupportedBrowser(false);
    const client = makeClient({});
    const out = await initialCheck(client);
    expect(out.kind).toBe("unsupported");
  });

  it("reports unconfigured when the server returns null public key", async () => {
    setSupportedBrowser(true);
    const client = makeClient({
      getWebPushPublicKey: jest.fn().mockResolvedValue(null),
    });
    const out = await initialCheck(client);
    expect(out.kind).toBe("unconfigured");
  });

  it("reports off when configured but no local subscription record", async () => {
    setSupportedBrowser(true);
    const client = makeClient({
      getWebPushPublicKey: jest
        .fn()
        .mockResolvedValue({ public_key: "k" }),
    });
    const out = await initialCheck(client);
    expect(out.kind).toBe("off");
  });

  it("recovers an 'on' state from localStorage when configured", async () => {
    setSupportedBrowser(true);
    window.localStorage.setItem("rentwise.webPushSubscriptionId", "42");
    const client = makeClient({
      getWebPushPublicKey: jest
        .fn()
        .mockResolvedValue({ public_key: "k" }),
    });
    const out = await initialCheck(client);
    expect(out).toEqual({ kind: "on", subscriptionId: 42 });
  });
});
