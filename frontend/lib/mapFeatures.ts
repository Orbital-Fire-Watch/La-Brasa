/** Converts API responses into GeoJSON for the map, with colours and popup texts already attached. */
import { cellToBoundary } from "h3-js";
import { AGE_COLOR, ageClass, divergingScale, sequentialScale, type AgeClass } from "./colors";
import { daysBetween, formatDate } from "./dates";
import type { FireUnit } from "./fireUnits";
import { formatCompact, formatInt, formatOne, formatSigned, relativeDays } from "./format";

interface CellLike {
  cell: string;
  fires: number;
  hotspots: number;
  frp_sum: number;
  first_seen?: string | null;
  last_seen?: string | null;
}

interface AnomalyLike {
  cell: string;
  value: number;
  median: number;
  diff: number;
  rank: number;
}

interface HotspotLike {
  id: number;
  geometry: { coordinates: [number, number] };
  properties: {
    time: string;
    sensor: string;
    confidence: string;
    frp: number | null;
    daynight: string;
    weight: number;
    province_id: string;
    event_id: string | null;
  };
}

const hexagon = (cell: string): GeoJSON.Polygon => {
  const ring = cellToBoundary(cell, true);
  return { type: "Polygon", coordinates: [[...ring, ring[0]]] };
};

const popup = (title: string, rows: [string, string][], eventId?: string | null) => JSON.stringify({ title, rows, eventId });

function cellRows(c: CellLike): [string, string][] {
  return [
    ["Hotspots (harmonisiert)", formatOne(c.fires)],
    ["FRP-Summe", `${formatCompact(c.frp_sum)} MW`],
    ["Hotspots (roh)", formatInt(c.hotspots)],
    ...(c.first_seen && c.last_seen ? ([["Zeitraum", `${formatDate(c.first_seen)} – ${formatDate(c.last_seen)}`]] as [string, string][]) : []),
  ];
}

/** Grid coloured by value (page 1). */
export function cellsByValue(cells: CellLike[], metric: "fires" | "frp_sum", max: number): GeoJSON.FeatureCollection {
  const color = sequentialScale(max);
  return {
    type: "FeatureCollection",
    features: cells.map((c) => ({
      type: "Feature",
      properties: { color: color(c[metric]), popup: popup("H3-Zelle", cellRows(c)) },
      geometry: hexagon(c.cell),
    })),
  };
}

/** Grid coloured by age relative to D, opacity by value (page 2, spec §7.7). */
export function cellsByAge(cells: CellLike[], metric: "fires" | "frp_sum", max: number, date: string): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: cells.map((c) => {
      const since = c.last_seen ? daysBetween(c.last_seen, date) : 0;
      const age = ageClass(since);
      const share = max > 0 ? Math.log1p(c[metric]) / Math.log1p(max) : 1;
      return {
        type: "Feature",
        properties: {
          color: AGE_COLOR[age],
          opacity: 0.35 + 0.55 * share,
          popup: popup(`H3-Zelle · zuletzt ${relativeDays(since)}`, cellRows(c)),
        },
        geometry: hexagon(c.cell),
      };
    }),
  };
}

export function anomalyCells(cells: AnomalyLike[], maxAbsDiff: number, unit: string): GeoJSON.FeatureCollection {
  const color = divergingScale(maxAbsDiff);
  return {
    type: "FeatureCollection",
    features: cells.map((c) => ({
      type: "Feature",
      properties: {
        color: color(c.diff),
        opacity: 0.8,
        popup: popup(c.diff > 0 ? "Mehr als üblich" : c.diff < 0 ? "Weniger als üblich" : "Wie üblich", [
          ["Wert im Fenster", `${formatOne(c.value)} ${unit}`],
          ["Median Vergleichsjahre", `${formatOne(c.median)} ${unit}`],
          ["Abweichung", `${formatSigned(c.diff)} ${unit}`],
          ["Platz", `${c.rank}`],
        ]),
      },
      geometry: hexagon(c.cell),
    })),
  };
}

const SENSOR_LABEL: Record<string, string> = {
  MODIS_TERRA: "MODIS Terra",
  MODIS_AQUA: "MODIS Aqua",
  VIIRS_SNPP: "VIIRS Suomi NPP",
  VIIRS_NOAA20: "VIIRS NOAA-20",
  VIIRS_NOAA21: "VIIRS NOAA-21",
};

export function hotspotPoints(
  features: HotspotLike[], date: string, provinceName: (id: string) => string, eventsAvailable: boolean,
): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: features.map((f) => {
      const day = f.properties.time.slice(0, 10);
      const since = daysBetween(day, date);
      return {
        type: "Feature",
        id: f.id,
        properties: {
          color: AGE_COLOR[ageClass(since)],
          popup: popup(
            `Hotspot · ${relativeDays(since)}`,
            [
              ["Zeit (UTC)", `${formatDate(day)}, ${f.properties.time.slice(11, 16)}`],
              ["Sensor", SENSOR_LABEL[f.properties.sensor] ?? f.properties.sensor],
              ["Confidence", f.properties.confidence === "high" ? "hoch" : "nominal"],
              ["FRP", f.properties.frp === null ? "–" : `${formatOne(f.properties.frp)} MW`],
              ["Aufnahme", f.properties.daynight === "D" ? "Tag" : "Nacht"],
              ["Gewicht", f.properties.weight.toLocaleString("de-DE", { maximumFractionDigits: 3 })],
              ["Provinz", provinceName(f.properties.province_id)],
            ],
            eventsAvailable ? f.properties.event_id : null,
          ),
        },
        geometry: { type: "Point", coordinates: f.geometry.coordinates },
      };
    }),
  };
}

export function unitAge(u: FireUnit): AgeClass {
  return u.days_since_last > 2 ? "ended" : ageClass(u.days_since_last);
}

/** Event outlines plus centroid markers (outlines are tiny at low zoom). */
export function eventShapes(units: FireUnit[]): { polygons: GeoJSON.FeatureCollection; points: GeoJSON.FeatureCollection } {
  const maxFrp = Math.max(1, ...units.map((u) => u.frp_sum));
  return {
    polygons: {
      type: "FeatureCollection",
      features: units.map((u) => {
        const age = unitAge(u);
        return {
          type: "Feature",
          properties: { id: u.id, color: AGE_COLOR[age], stroke: age === "ended" ? "#757575" : "#7f2704", opacity: age === "ended" ? 0.3 : 0.6 },
          geometry: u.geometry,
        };
      }),
    },
    points: {
      type: "FeatureCollection",
      features: units.map((u) => {
        const age = unitAge(u);
        return {
          type: "Feature",
          properties: { id: u.id, color: AGE_COLOR[age], radius: 4 + 10 * Math.sqrt(u.frp_sum / maxFrp), opacity: age === "ended" ? 0.45 : 0.9 },
          geometry: { type: "Point", coordinates: u.centroid },
        };
      }),
    },
  };
}
