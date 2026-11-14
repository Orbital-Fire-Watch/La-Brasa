/**
 * Remembers drawn areas in sessionStorage. The API only has POST /api/areas, so after a reload the
 * geometry is needed to show the outline and to register the area again on AREA_NOT_FOUND (spec §6.3).
 */
import type { Geometry } from "./api/types";

const PREFIX = "la-brasa:area:";
export const LOCAL_AREA_ID = "local";

export function saveAreaGeometry(id: string, geometry: Geometry): void {
  try {
    sessionStorage.setItem(PREFIX + id, JSON.stringify(geometry));
  } catch {
    // storage full or blocked – the area still works until the page is reloaded
  }
}

export function loadAreaGeometry(id: string): Geometry | null {
  try {
    const raw = sessionStorage.getItem(PREFIX + id);
    return raw ? (JSON.parse(raw) as Geometry) : null;
  } catch {
    return null;
  }
}
