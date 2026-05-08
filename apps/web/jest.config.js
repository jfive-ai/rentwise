/** @type {import('jest').Config} */
module.exports = {
  preset: "jest-expo",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  transformIgnorePatterns: [
    "node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent|-modules-core|-router|-linking|-constants|-status-bar)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|@react-native-async-storage)/.*)",
  ],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },
  collectCoverageFrom: [
    "src/**/*.{ts,tsx}",
    "!src/**/__tests__/**",
    "!src/**/*.d.ts",
    // MapView.tsx is a thin web-only shell over MapLibre. The mount
    // useEffect needs a real DOM ref + a WebGL context that jsdom can't
    // provide, so jest can't exercise it. The pure helpers it calls
    // (src/lib/mapClusters.ts) are fully covered, and Playwright runs
    // the real-browser path in Phase 7 PR-C's E2E.
    "!src/components/MapView.tsx",
  ],
  coverageThreshold: {
    global: {
      branches: 75,
      lines: 80,
      statements: 80,
    },
  },
  testPathIgnorePatterns: ["/node_modules/", "/e2e/", "/.expo/"],
};
