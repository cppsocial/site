import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: ["frontend/src/**/*.ts"],
      exclude: ["frontend/src/**/*.d.ts"],
      reporter: ["text", "json-summary", "html"],
    },
  },
});
