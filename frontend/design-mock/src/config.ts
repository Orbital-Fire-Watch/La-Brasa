/** Settings of the design mock, read once. Everything here is public (bundled into the client). */
import defaultLogo from "../assets/la-brasa-logo.svg";

export const BRAND = {
  name: "La Brasa",
  /** Logo shown top left (marked "AI generated" in the image itself). Pass another path or URL with VITE_LOGO_URL. */
  logoUrl: String(import.meta.env.VITE_LOGO_URL || defaultLogo),
} as const;

/** Start page: info boxes slide in this long after the page opened ... */
export const INFO_INITIAL_DELAY_MS = 2000;
/** ... and come back this long after the map stopped moving. */
export const INFO_IDLE_DELAY_MS = 2000;

/** Window of the activity map and the info boxes on the start page. */
export const MAP_WINDOW_DAYS = 30;

/**
 * Smaller H3 cells: resolution = zoom − 1 (the app uses zoom − 2), limited to 4–8.
 * At the Iberia overview (zoom ≈ 5) this is resolution 4 (≈ 1 770 km²) instead of 3 (≈ 12 400 km²).
 */
export const H3_ZOOM_OFFSET = -1;
export const H3_MIN_RESOLUTION = 4;

export function fineResolutionForZoom(zoom: number, max = 8): number {
  return Math.max(H3_MIN_RESOLUTION, Math.min(max, Math.round(zoom) + H3_ZOOM_OFFSET));
}

/** Path of the simple info page next to the mock. */
export const INFO_PAGE_URL = "info.html";
