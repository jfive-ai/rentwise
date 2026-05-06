import "@testing-library/jest-native/extend-expect";

// AsyncStorage doesn't exist in jsdom; use the official mock.
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock")
);

// Silence the react-native warning about unrecognized event names in tests.
jest.mock("react-native/Libraries/Animated/NativeAnimatedHelper");
