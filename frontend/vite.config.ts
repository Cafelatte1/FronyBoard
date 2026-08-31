import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// In dev, /api is proxied to a running aira server (default: local backend).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": process.env.AIRA_API ?? "http://127.0.0.1:8642",
    },
  },
  test: {
    environment: "jsdom",
    globals: true, // lets testing-library auto-cleanup between tests
    setupFiles: "./tests/setup.ts",
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
