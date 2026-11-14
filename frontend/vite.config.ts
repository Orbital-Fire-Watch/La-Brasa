import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // Spec §11: in development the backend runs on :8000, the proxy avoids CORS
    proxy: { "/api": "http://localhost:8000" },
  },
  build: {
    chunkSizeWarningLimit: 1500,
  },
  test: {
    include: ["lib/**/*.test.ts", "services/**/*.test.ts"],
  },
});
