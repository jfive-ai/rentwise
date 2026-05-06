import "@testing-library/react-native/extend-expect";

// AsyncStorage doesn't exist in jsdom; use the official mock.
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock")
);

// Silence the react-native warning about unrecognized event names in tests.
// NativeAnimatedHelper was removed in react-native 0.76; mock the module that replaced it.
jest.mock("react-native/Libraries/Animated/NativeAnimatedModule");
