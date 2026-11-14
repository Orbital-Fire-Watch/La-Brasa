import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // Spec §11: in development the backend runs on :8000, the proxy avoids CORS
    proxy: { "/api": "http://localhost:8000" },
  },
  // MapLibre and the mock API start their workers as ES modules ({ type: "module" })
  worker: { format: "es" },
  build: {
    chunkSizeWarningLimit: 1100,    // MapLibre alone is about 1.1 MB (300 KB gzip) and cannot be split further
    rollupOptions: {
      // The app and the plain info page it links to (lib/uiConfig.ts INFO_PAGE_URL)
      input: { main: "index.html", info: "info.html" },
      output: {
        // Libraries in their own files: they change less often than the app, so browsers keep them cached
        manualChunks(id) {
          if (id.includes("node_modules/maplibre-gl")) return "maplibre";
          if (id.includes("node_modules/h3-js")) return "h3";
          if (/node_modules\/(d3-|internmap)/.test(id)) return "d3";
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return "react";
        },
      },
    },
  },
  test: {
    include: ["lib/**/*.test.ts", "services/**/*.test.ts"],
  },
});
