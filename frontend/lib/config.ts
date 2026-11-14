/** Typed app configuration, read once from the Vite environment (all values are public). */

export type ApiMode = "mock" | "live";

const env = import.meta.env;

export const CONFIG = {
  /** "mock" answers from the in-browser mock API (default while the backend is being built). */
  apiMode: (env.VITE_API_MODE === "live" ? "live" : "mock") as ApiMode,
  /** Origin of the backend; empty = same origin (Vite proxy in dev, Caddy in production). */
  apiBaseUrl: String(env.VITE_API_URL ?? "").replace(/\/$/, ""),
  requestTimeoutMs: 30_000,
  /** Mock only: comma-separated `features` to switch off, e.g. "events,areas" to test the fallbacks. */
  mockDisabledFeatures: String(env.VITE_MOCK_DISABLE ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
  /** Free vector basemap without API key (OpenFreeMap, data © OpenStreetMap contributors). */
  basemapStyleUrl: String(env.VITE_BASEMAP_STYLE_URL || "https://tiles.openfreemap.org/styles/positron"),
  /** Raster tiles for the satellite view ({z}/{y}/{x} template, no API key) and their attribution. */
  satelliteTilesUrl: String(
    env.VITE_SATELLITE_TILES_URL || "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  ),
  satelliteAttribution: String(env.VITE_SATELLITE_ATTRIBUTION || "Imagery © Esri, Maxar, Earthstar Geographics"),
} as const;
