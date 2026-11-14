/** The user-facing settings shared by both pages (spec §2 "Methode", "Confidence", §7.1). */
import type { SeriesKey } from "./analysis";

export type Method = "fires" | "frp_sum" | "events";
export const METHODS: readonly Method[] = ["fires", "frp_sum", "events"];

export const METHOD_LABEL: Record<Method, string> = {
  fires: "Hotspots",
  frp_sum: "FRP",
  events: "Ereignisse",
};

/** Names from spec §7.7 */
export const METHOD_LONG: Record<Method, string> = {
  fires: "harmonisierte Hotspots",
  frp_sum: "FRP-Summe (harmonisiert, MW)",
  events: "neue Ereignisse",
};

export const METHOD_HELP: Record<Method, string> = {
  fires:
    "Summe der harmonisierten Gewichte: MODIS-Aqua-äquivalente Hotspots. Jahre mit unterschiedlicher Satellitenflotte bleiben vergleichbar.",
  frp_sum: "Fire Radiative Power, harmonisiert: durchschnittliche FRP-Summe pro aktivem Sensor in Megawatt.",
  events:
    "Ereignisse = räumlich und zeitlich zusammenhängende Hotspots (wahrscheinlich derselbe Brand). Anzahl hängt von der Satellitenflotte ab, Jahre nur eingeschränkt vergleichbar.",
};

export function seriesKeyFor(method: Method): SeriesKey {
  return method === "events" ? "events_new" : method;
}

/** Grid cells have no event counts – the map colours by fires in "events" mode. */
export function gridMetricFor(method: Method): "fires" | "frp_sum" {
  return method === "frp_sum" ? "frp_sum" : "fires";
}

/** Events are only shown for long-term comparisons from the VIIRS era on (spec §5.6). */
export const EVENTS_COMPARABLE_FROM_YEAR = 2012;

export type ConfidenceLevel = "nominal" | "high";
export const CONFIDENCE_LABEL: Record<ConfidenceLevel, string> = {
  nominal: "Standard",
  high: "nur hohe Sicherheit",
};
export const CONFIDENCE_HELP: Record<ConfidenceLevel, string> = {
  nominal: "Punkte mit Confidence „nominal“ oder „high“ (Standard).",
  high: "Nur Punkte mit hoher Erkennungssicherheit. Werte nicht mit der Standardansicht vergleichen.",
};

export type Lookback = 1 | 7 | 14;
export const LOOKBACKS: readonly Lookback[] = [1, 7, 14];
export const lookbackLabel = (l: Lookback): string => (l === 1 ? "1 Tag" : `${l} Tage`);

/** Zoom → H3 resolution (spec §4): resolution = zoom − 2, limited to 3–8. */
export function resolutionForZoom(zoom: number, max = 8): number {
  return Math.max(3, Math.min(max, Math.round(zoom) - 2));
}
export const HOTSPOT_MIN_ZOOM = 11;

/** Time slider range around D₀ (spec §4). */
export const SLIDER_RANGE_DAYS = 60;
