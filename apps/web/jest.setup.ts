import "@testing-library/react-native/extend-expect";

// AsyncStorage doesn't exist in jsdom; use the official mock.
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock")
);

// Silence the react-native warning about unrecognized event names in tests.
// NativeAnimatedHelper was removed in react-native 0.76; mock the module that replaced it.
jest.mock("react-native/Libraries/Animated/NativeAnimatedModule");

// Phase 7 PR-A: maplibre-gl ships native WebGL; jsdom can't run it.
// Suite-wide mock so MapView tests + downstream consumers (SearchScreen)
// don't have to opt in. Per-test specifics override via spyOn / mockImpl.
jest.mock("maplibre-gl", () => {
  class FakeMap {
    private source: { setData: jest.Mock; getClusterExpansionZoom: jest.Mock } | null = null;
    // No-op stubs so production code that calls these (highlight, fit
    // bounds, etc.) doesn't throw under jsdom. The mount-effect that
    // would actually invoke them never runs in react-test-renderer
    // because the inner <div> ref doesn't bind, so these are guards
    // only — tests cover the helpers directly.
    fitBounds = jest.fn();
    setLayoutProperty = jest.fn();
    setPaintProperty = jest.fn();
    on(event: string, layerOrHandler: unknown, handler?: unknown) {
      // Fire the 'load' handler synchronously the moment the production
      // code registers it. That lets the inner addSource / addLayer /
      // moveend-binding paths run under jsdom even though there's no
      // real WebGL context. Other event handlers are dropped.
      const fn = typeof layerOrHandler === "function" ? layerOrHandler : handler;
      if (event === "load" && typeof fn === "function") {
        fn();
      }
      return this;
    }
    addSource() {
      this.source = {
        setData: jest.fn(),
        getClusterExpansionZoom: jest.fn().mockResolvedValue(14),
      };
    }
    addLayer() {}
    getSource() {
      return this.source ?? undefined;
    }
    getBounds() {
      return {
        getWest: () => -123.2,
        getSouth: () => 49.2,
        getEast: () => -123.0,
        getNorth: () => 49.3,
      };
    }
    easeTo() {}
    remove() {}
  }
  return {
    __esModule: true,
    default: { Map: FakeMap },
    Map: FakeMap,
  };
});

// Avoid jest balking at the side-effect CSS import in MapView.
jest.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}), { virtual: true });
