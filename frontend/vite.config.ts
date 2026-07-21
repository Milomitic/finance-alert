/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    // jsdom for component tests; the pure-lib tests are env-agnostic and still
    // pass. Explicit vitest imports are kept (no `globals`), so no tsconfig
    // types change is needed.
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
  build: {
    rollupOptions: {
      output: {
        // Split the always-loaded framework libs into their own stable vendor
        // chunk. These rarely change between deploys, so isolating them lets
        // browsers keep them cached across app-code releases. Page-specific
        // heavy deps (lightweight-charts, recharts) are already isolated by
        // the per-route React.lazy splits in App.tsx, so they don't need
        // manual entries here.
        manualChunks(id) {
          if (
            /[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/.test(
              id,
            )
          ) {
            return "react-vendor";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
