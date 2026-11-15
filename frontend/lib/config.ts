/** Typed app configuration, read once from the Vite environment (all values are public). */

const env = import.meta.env;

export const CONFIG = {
  /** Origin of the backend; empty = same origin (Vite proxy in dev, Caddy in production). */
  apiBaseUrl: String(env.VITE_API_URL ?? "").replace(/\/$/, ""),
  requestTimeoutMs: 30_000,
  /** Free vector basemap without API key (OpenFreeMap, data © OpenStreetMap contributors). */
  basemapStyleUrl: String(env.VITE_BASEMAP_STYLE_URL || "https://tiles.openfreemap.org/styles/positron"),
  /** Raster tiles for the satellite view ({z}/{y}/{x} template, no API key) and their attribution. */
  satelliteTilesUrl: String(
    env.VITE_SATELLITE_TILES_URL || "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  ),
  satelliteAttribution: String(env.VITE_SATELLITE_ATTRIBUTION || "Imagery © Esri, Maxar, Earthstar Geographics"),
} as const;
