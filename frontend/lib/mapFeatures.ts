/** GeoJSON for the maps, with translated popups and palette-aware colours. */
import type * as GeoJSON from "geojson";
import { cellToBoundary } from "h3-js";
import { ageClass, divergingScale, type AgeClass } from "./colors";
import { daysBetween } from "./dates";
import type { FireUnit } from "./fireUnits";
import type { AnomalyCell, GridCell, HotspotFeature } from "../services/api/types";
import type { Fmt, Translate } from "../i18n/I18n";


/** Outline of fires probably hidden under clouds (the warning colour of the cloud note). */
export const HIDDEN_COLOR = "#e3b341";
export interface PopupData {
  title: string;
  rows: [string, string][];
  eventId?: string | null;
}

interface Tx {
  t: Translate;
  f: Fmt;
}

const SENSOR: Record<string, string> = {
  MODIS_TERRA: "MODIS Terra",
  MODIS_AQUA: "MODIS Aqua",
  VIIRS_SNPP: "VIIRS Suomi NPP",
  VIIRS_NOAA20: "VIIRS NOAA-20",
  VIIRS_NOAA21: "VIIRS NOAA-21",
};

const hexagon = (cell: string): GeoJSON.Polygon => ({ type: "Polygon", coordinates: [cellToBoundary(cell, true)] });
const popup = (data: PopupData) => JSON.stringify(data);

function cellRows(c: GridCell, { t, f }: Tx): [string, string][] {
  const rows: [string, string][] = [
    [t("pop.firesHarm"), f.one(c.fires)],
    [t("pop.frpSum"), `${f.compact(c.frp_sum)} MW`],
    [t("pop.raw"), f.int(c.hotspots)],
  ];
  if (c.first_seen && c.last_seen) rows.push([t("pop.period"), t("pop.range", { start: f.date(c.first_seen), end: f.date(c.last_seen) })]);
  return rows;
}

export function cellsByValue(cells: GridCell[], metric: "fires" | "frp_sum", color: (v: number) => string, tx: Tx): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: cells.map((c) => ({
      type: "Feature",
      properties: { color: color(c[metric]), popup: popup({ title: tx.t("pop.cell"), rows: cellRows(c, tx) }) },
      geometry: hexagon(c.cell),
    })),
  };
}

export function cellsByAge(
  cells: GridCell[], metric: "fires" | "frp_sum", max: number, date: string, colors: Record<AgeClass, string>, tx: Tx,
): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: cells.map((c) => {
      const since = c.last_seen ? daysBetween(c.last_seen, date) : 0;
      const share = max > 0 ? Math.log1p(c[metric]) / Math.log1p(max) : 1;
      return {
        type: "Feature",
        properties: {
          color: colors[ageClass(since)],
          opacity: 0.35 + 0.55 * share,
          popup: popup({ title: tx.t("pop.cellLastSeen", { when: tx.f.daysAgo(since) }), rows: cellRows(c, tx) }),
        },
        geometry: hexagon(c.cell),
      };
    }),
  };
}

export function anomalyCells(cells: AnomalyCell[], maxAbsDiff: number, unit: string, { t, f }: Tx): GeoJSON.FeatureCollection {
  const color = divergingScale(maxAbsDiff);
  return {
    type: "FeatureCollection",
    features: cells.map((c) => ({
      type: "Feature",
      properties: {
        color: color(c.diff),
        opacity: 0.8,
        popup: popup({
          title: t(c.diff > 0 ? "pop.more" : c.diff < 0 ? "pop.less" : "pop.same"),
          rows: [
            [t("pop.value"), `${f.one(c.value)} ${unit}`],
            [t("pop.median"), `${f.one(c.median)} ${unit}`],
            [t("pop.diff"), `${f.signed(c.diff)} ${unit}`],
            [t("pop.rank"), f.int(c.rank)],
          ],
        }),
      },
      geometry: hexagon(c.cell),
    })),
  };
}

export function hotspotPoints(
  features: HotspotFeature[], date: string, regionName: (id: string) => string, colors: Record<AgeClass, string>, eventsAvailable: boolean,
  { t, f }: Tx,
): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: features.map((h) => {
      const day = h.properties.time.slice(0, 10);
      const since = daysBetween(day, date);
      return {
        type: "Feature",
        id: h.id,
        properties: {
          color: colors[ageClass(since)],
          popup: popup({
            title: t("pop.hotspot", { when: f.daysAgo(since) }),
            rows: [
              [t("pop.time"), `${f.date(day)}, ${h.properties.time.slice(11, 16)}`],
              [t("pop.sensor"), SENSOR[h.properties.sensor] ?? h.properties.sensor],
              [t("pop.conf"), t(h.properties.confidence === "high" ? "pop.confHigh" : "pop.confNominal")],
              ["FRP", h.properties.frp == null ? t("ui.na") : `${f.one(h.properties.frp)} MW`],
              [t("pop.pass"), t(h.properties.daynight === "D" ? "pop.day" : "pop.night")],
              [t("pop.area"), regionName(h.properties.province_id)],
            ],
            eventId: eventsAvailable ? h.properties.event_id : null,
          }),
        },
        geometry: { type: "Point", coordinates: h.geometry.coordinates },
      };
    }),
  };
}

export function unitAge(u: FireUnit): AgeClass {
  return u.days_since_last > 2 ? "ended" : ageClass(u.days_since_last);
}

/** `hidden`: fires probably hidden under clouds on D (lib/clouds.ts), drawn dashed and faint. */
export function eventShapes(units: FireUnit[], colors: Record<AgeClass, string>, hidden: (u: FireUnit) => boolean = () => false) {
  const maxFrp = Math.max(1, ...units.map((u) => u.frp_sum));
  const polygons: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: units.map((u) => {
      const age = unitAge(u);
      return {
        type: "Feature",
        properties: { id: u.id, color: colors[age], stroke: age === "ended" ? "#757575" : "#3f1d0b", opacity: hidden(u) ? 0.15 : age === "ended" ? 0.3 : 0.6, hidden: hidden(u) },
        geometry: u.geometry,
      };
    }),
  };
  const points: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: units.map((u) => {
      const age = unitAge(u);
      return {
        type: "Feature",
        properties: {
          id: u.id, color: colors[age], radius: 4 + 10 * Math.sqrt(u.frp_sum / maxFrp), opacity: hidden(u) ? 0.3 : age === "ended" ? 0.45 : 0.9,
          ...(hidden(u) ? { ring: HIDDEN_COLOR, ringWidth: 2 } : {}),
        },
        geometry: { type: "Point", coordinates: u.centroid },
      };
    }),
  };
  return { polygons, points };
}

/** Raw detections of one sensor family per H3 cell (MODIS or VIIRS view and the comparison maps). */
export function rawCells(
  cells: { cell: string; count: number; frpSum: number }[], color: (v: number) => string, title: string, { t, f }: Tx,
): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: cells.map((c) => ({
      type: "Feature",
      properties: {
        color: color(c.count),
        popup: popup({ title, rows: [[t("cmp.detections"), f.int(c.count)], [t("pop.frpSum"), `${f.compact(c.frpSum)} MW`]] }),
      },
      geometry: hexagon(c.cell),
    })),
  };
}
