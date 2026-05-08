# RentWise Web

React + Expo Router (universal: web, iOS, macOS) + TypeScript strict. See the [root README](../../README.md) for the project overview and Quick Start.

## Run

```bash
npm install
npm run web        # web at http://localhost:8081
npm run ios        # iOS simulator (requires Xcode)
npm run android    # Android emulator
```

Set `EXPO_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8000`) if your backend isn't on the default port.

## Test

```bash
npm run typecheck                 # tsc --noEmit
npm run lint                      # eslint
npm test                          # Jest unit + component tests
npm run test:coverage             # with coverage gate (≥80% / ≥75%)
npx playwright install            # one-time browser download
npx playwright test               # E2E
```

Jest coverage thresholds (`jest.config.js`):

- statements: 80
- branches: 75

E2E specs live under `e2e/` and run against a Vite-built dev bundle started by Playwright (no backend required — fixtures stub the API).

## Layout

```
src/
├── api/
│   ├── client.ts          # ApiClient with search / saveSearch / settings
│   └── types.ts           # Mirrors apps/api/rentwise/models.py
├── components/
│   ├── FilterPanel.tsx
│   ├── ListingCard.tsx
│   ├── SaveSearchForm.tsx
│   ├── SavedSearchesDrawer.tsx
│   └── ...
├── llm/                   # Provider list + key validation
├── lib/                   # Pure helpers (cluster grouping, ...)
├── screens/
│   ├── SearchScreen.tsx
│   ├── SettingsScreen.tsx
│   └── FirstRunWizard.tsx
├── state/                 # QueryProvider (in-memory NormalizedQuery state)
├── storage/               # AsyncStorage-backed listing actions (save / hide / contacted)
└── theme.ts
app/                       # expo-router screens (thin wrappers around src/screens)
```

## Style

- TypeScript strict; never `any` to silence the compiler.
- Functional components + hooks. No class components.
- `react-native` primitives only (`View`, `Text`, `ScrollView`, `Pressable`, …) — they render correctly on web, iOS, macOS.
- Don't add `localStorage` / `document` access without a `Platform.OS === "web"` guard.
- Run `npx tsc --noEmit` before pushing — the CI typecheck is strict.
