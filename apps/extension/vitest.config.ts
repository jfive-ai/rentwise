import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: false,
    include: ["tests/**/*.test.ts"],
  },
  resolve: {
    alias: { "@": resolve(__dirname, "src") },
  },
});
