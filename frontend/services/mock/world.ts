/**
 * Synthetic but plausible fire world for the mock API: events with a season profile per region,
 * a changing satellite fleet and harmonised weights exactly as in spec §5.2/§5.5.
 * Everything is deterministic, so the same request always gets the same answer.
 */
import type { RegionFeature, RegionsResponse, Sensor } from "../api/types";
import { addDays, dayOfYear, daysBetween, toIso, toMs, DAY_MS, yearOf } from "../../lib/dates";
import { bboxOf, pointInGeometry, type BBox, type Position } from "../../lib/geo";
import { hashString, hex12, mulberry32, normal, poisson, type Rng } from "./rng";
import { latLngToCell } from "h3-js";

export const FIRST_DATE = "2000-11-01";

export interface SensorSpan {
  id: Sensor;
  from: string;
  to: string | null;
}

export const SENSORS: SensorSpan[] = [
  { id: "MODIS_TERRA", from: "2000-11-01", to: null },
  { id: "MODIS_AQUA", from: "2002-07-04", to: null },
  { id: "VIIRS_SNPP", from: "2012-01-20", to: "2026-11-02" },
  { id: "VIIRS_NOAA20", from: "2018-04-01", to: null },
  { id: "VIIRS_NOAA21", from: "2024-01-17", to: null },
];

/** k_sensor (spec §5.2): converts each sensor to MODIS-Aqua-equivalent hotspots. */
export const K_SENSOR: Record<Sensor, number> = {
  MODIS_TERRA: 0.9,
  MODIS_AQUA: 1,
  VIIRS_SNPP: 0.25,
  VIIRS_NOAA20: 0.25,
  VIIRS_NOAA21: 0.25,
};

/** Overpass times (UTC hour.minutes) for day and night. */
const OVERPASS: Record<Sensor, [number, number]> = {
  MODIS_TERRA: [10.5, 22.5],
  MODIS_AQUA: [13.5, 1.5],
  VIIRS_SNPP: [13.5, 1.5],
  VIIRS_NOAA20: [12.7, 0.7],
  VIIRS_NOAA21: [13.3, 1.3],
};

export interface MockHotspot {
  id: number;
  lon: number;
  lat: number;
  date: string;
  time: string;
  sensor: Sensor;
  confidence: "nominal" | "high";
  confidenceRaw: string;
  frp: number;
  frpH: number;
  daynight: "D" | "N";
  weight: number;
  nActive: number;
}

export interface EventDayAgg {
  hotspots: number;
  fires: number;
  frp: number;
  frpMax: number;
}

export interface MockEventDay {
  idx: number;
  event: number;
  day: number;
  center: Position;
  spreadKm: number;
  /** expected hotspots per active sensor-rate unit */
  intensity: number;
  seed: number;
  idBase: number;
  bbox: BBox;
  all: EventDayAgg;
  high: EventDayAgg;
}

export interface MockEvent {
  idx: number;
  id: string;
  origin: Position;
  provinceId: string;
  regionId: string;
  countryId: string;
  /** event-day indices in date order; only days with at least one hotspot */
  days: number[];
}

export interface World {
  firstDate: string;
  lastDate: string;
  nDays: number;
  nActive: Uint8Array;
  events: MockEvent[];
  eventDays: MockEventDay[];
  byDay: number[][];
  eventById: Map<string, MockEvent>;
  regions: RegionsResponse;
  regionById: Map<string, RegionFeature>;
  locate: (p: Position) => RegionFeature | null;
}

interface Zone {
  center: Position;
  sigmaKm: number;
  weight: number;
  /** [peak day of year, width in days, relative height] */
  peaks: [number, number, number][];
}

const NW: [number, number, number][] = [[75, 20, 0.7], [225, 22, 1], [285, 10, 0.25]];
const SUMMER: [number, number, number][] = [[210, 30, 1], [100, 25, 0.12]];

const ZONES: Zone[] = [
  { center: [-7.6, 42.25], sigmaKm: 45, weight: 1.6, peaks: NW }, // Ourense
  { center: [-7.4, 42.9], sigmaKm: 50, weight: 1.0, peaks: NW }, // Lugo
  { center: [-8.5, 42.5], sigmaKm: 40, weight: 0.8, peaks: NW }, // Pontevedra / A Coruña
  { center: [-6.3, 43.3], sigmaKm: 50, weight: 0.8, peaks: NW }, // Asturias
  { center: [-6.3, 42.4], sigmaKm: 55, weight: 0.9, peaks: NW }, // León / Zamora
  { center: [-7.9, 41.6], sigmaKm: 50, weight: 1.6, peaks: NW }, // Norte (PT)
  { center: [-7.9, 40.3], sigmaKm: 55, weight: 1.5, peaks: SUMMER }, // Centro (PT)
  { center: [-8.0, 38.6], sigmaKm: 60, weight: 0.6, peaks: SUMMER }, // Alentejo
  { center: [-8.3, 37.3], sigmaKm: 30, weight: 0.3, peaks: SUMMER }, // Algarve
  { center: [-6.2, 39.7], sigmaKm: 70, weight: 0.8, peaks: SUMMER }, // Extremadura
  { center: [-5.5, 37.6], sigmaKm: 90, weight: 0.8, peaks: SUMMER }, // Andalucía
  { center: [-3.6, 39.5], sigmaKm: 100, weight: 0.6, peaks: SUMMER }, // Castilla-La Mancha
  { center: [-4.4, 41.3], sigmaKm: 100, weight: 0.5, peaks: SUMMER }, // Castilla y León (south)
  { center: [-0.7, 39.2], sigmaKm: 60, weight: 0.5, peaks: SUMMER }, // Valencia
  { center: [-1.5, 38.1], sigmaKm: 50, weight: 0.3, peaks: SUMMER }, // Murcia
  { center: [-0.8, 41.6], sigmaKm: 80, weight: 0.4, peaks: SUMMER }, // Aragón
  { center: [1.4, 41.8], sigmaKm: 60, weight: 0.4, peaks: SUMMER }, // Cataluña
  { center: [2.9, 39.6], sigmaKm: 25, weight: 0.1, peaks: SUMMER }, // Mallorca
];

/** Well-known bad years get a fixed boost so the demo shows recognisable peaks. */
const YEAR_BOOST: Record<number, number> = {
  2003: 1.5, 2005: 1.7, 2006: 1.3, 2012: 1.4, 2013: 1.2, 2016: 1.4, 2017: 2.0, 2022: 1.6, 2024: 0.8, 2025: 1.7, 2026: 0.9,
};

/** Big single fires: [start, lon, lat, intensity, duration] */
const BIG_FIRES: [string, number, number, number, number][] = [
  ["2003-08-02", -7.6, 39.9, 220, 12],
  ["2005-08-08", -8.1, 40.4, 180, 10],
  ["2006-08-05", -8.4, 42.6, 160, 9],
  ["2012-08-29", -0.9, 39.1, 200, 8],
  ["2017-06-17", -8.2, 39.95, 260, 6],
  ["2017-10-15", -8.0, 40.5, 300, 4],
  ["2017-10-15", -7.6, 42.1, 220, 4],
  ["2022-06-15", -6.4, 41.95, 240, 9],
  ["2022-07-17", -6.3, 41.85, 220, 11],
  ["2025-08-10", -7.25, 42.3, 300, 12],
  ["2025-08-11", -6.5, 42.45, 260, 13],
  ["2025-08-12", -7.1, 40.35, 240, 10],
];

const EVENTS_PER_YEAR = 1600;
const OUTAGE_PROBABILITY = 0.002;

function activeSensors(date: string): SensorSpan[] {
  return SENSORS.filter((s) => s.from <= date && (s.to === null || s.to >= date));
}

function seasonProfile(zone: Zone, doy: number): number {
  let v = 0.08;
  for (const [peak, width, height] of zone.peaks) {
    const d = Math.min(Math.abs(doy - peak), 365 - Math.abs(doy - peak));
    v += height * Math.exp(-(d * d) / (2 * width * width));
  }
  return v;
}

const kmToDeg = (km: number, lat: number): [number, number] => [km / (111.32 * Math.cos((lat * Math.PI) / 180)), km / 110.57];

function makeLocator(regions: RegionsResponse) {
  const provinces = regions.features
    .filter((f) => f.properties.level === "province")
    .map((f) => ({ f, bbox: bboxOf(f.geometry) }));
  return (p: Position): RegionFeature | null => {
    for (const { f, bbox } of provinces) {
      if (p[0] < bbox[0] || p[0] > bbox[2] || p[1] < bbox[1] || p[1] > bbox[3]) continue;
      if (pointInGeometry(p, f.geometry)) return f;
    }
    return null;
  };
}

/** Points of one event-day. Called at build time for the sums and again on demand (same seed → same points). */
export function hotspotsOf(world: Pick<World, "firstDate" | "nActive">, ed: MockEventDay): MockHotspot[] {
  const date = addDays(world.firstDate, ed.day);
  return generateHotspots(ed, date, world.nActive[ed.day], true);
}

/** `full = false` skips the string fields – used while building the world, where only the sums matter. */
function generateHotspots(ed: MockEventDay, date: string, nActive: number, full: boolean): MockHotspot[] {
  if (nActive === 0) return [];
  const rng = mulberry32(ed.seed);
  const sensors = activeSensors(date);
  const rates = sensors.map((s) => 1 / K_SENSOR[s.id]);
  const rateSum = rates.reduce((a, b) => a + b, 0);
  const expected = ed.intensity * rateSum;
  const [dLon, dLat] = kmToDeg(ed.spreadKm, ed.center[1]);
  const n = poisson(rng, expected);
  const out: MockHotspot[] = [];
  const pHigh = Math.min(0.8, 0.15 + 0.1 * Math.log1p(ed.intensity));
  for (let i = 0; i < n; i++) {
    let r = rng() * rateSum;
    let s = sensors[0];
    for (let j = 0; j < sensors.length; j++) {
      r -= rates[j];
      if (r <= 0) {
        s = sensors[j];
        break;
      }
    }
    const lon = ed.center[0] + normal(rng) * dLon;
    const lat = ed.center[1] + normal(rng) * dLat;
    const day = rng() < 0.75;
    const hour = OVERPASS[s.id][day ? 0 : 1] + (rng() - 0.5) * 0.6;
    const high = rng() < pHigh;
    const isModis = s.id.startsWith("MODIS");
    const mu = (isModis ? 2.7 : 1.6) + 0.15 * Math.log1p(ed.intensity);
    const frp = Math.round(Math.exp(mu + 0.9 * normal(rng)) * 10) / 10;
    const modisConf = high ? 80 + Math.floor(rng() * 21) : 30 + Math.floor(rng() * 50);
    out.push({
      id: ed.idBase + i,
      lon: full ? Math.round(lon * 1e4) / 1e4 : lon,
      lat: full ? Math.round(lat * 1e4) / 1e4 : lat,
      date,
      time: full ? timeString(date, hour) : "",
      sensor: s.id,
      confidence: high ? "high" : "nominal",
      confidenceRaw: !full ? "" : isModis ? String(modisConf) : high ? "h" : "n",
      frp,
      frpH: frp / nActive,
      daynight: day ? "D" : "N",
      weight: K_SENSOR[s.id] / nActive,
      nActive,
    });
  }
  return out;
}

function timeString(date: string, hour: number): string {
  const h = (hour + 24) % 24;
  const hh = Math.floor(h);
  const mm = Math.floor((h - hh) * 60);
  return `${date}T${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:00Z`;
}

const emptyAgg = (): EventDayAgg => ({ hotspots: 0, fires: 0, frp: 0, frpMax: 0 });

function addPoint(agg: EventDayAgg, h: MockHotspot) {
  agg.hotspots++;
  agg.fires += h.weight;
  agg.frp += h.frpH;
  agg.frpMax = Math.max(agg.frpMax, h.frp);
}

interface Seed {
  start: number;
  origin: Position;
  province: RegionFeature;
  intensity: number;
  duration: number;
}

export function buildWorld(regions: RegionsResponse, lastDate: string): World {
  const rng: Rng = mulberry32(20261114);
  const locate = makeLocator(regions);
  const regionById = new Map(regions.features.map((f) => [f.properties.id, f]));
  const nDays = daysBetween(FIRST_DATE, lastDate) + 1;

  const nActive = new Uint8Array(nDays);
  for (let d = 0; d < nDays; d++) {
    const date = addDays(FIRST_DATE, d);
    nActive[d] = rng() < OUTAGE_PROBABILITY && d < nDays - 30 ? 0 : activeSensors(date).length;
  }

  const yearFactor = new Map<number, number>();
  for (let y = yearOf(FIRST_DATE); y <= yearOf(lastDate); y++) {
    yearFactor.set(y, (YEAR_BOOST[y] ?? 1) * Math.exp(0.25 * normal(rng)));
  }

  const zoneNorm = ZONES.map((z) => {
    let s = 0;
    for (let doy = 1; doy <= 365; doy++) s += seasonProfile(z, doy);
    return s / 365;
  });
  const weightSum = ZONES.reduce((s, z) => s + z.weight, 0);
  const basePerDay = EVENTS_PER_YEAR / 365;

  const seeds: Seed[] = [];
  const t0 = toMs(FIRST_DATE);
  for (let d = 0; d < nDays; d++) {
    const date = toIso(t0 + d * DAY_MS);
    const doy = dayOfYear(date);
    const yf = yearFactor.get(yearOf(date)) ?? 1;
    const dayNoise = Math.exp(0.6 * normal(rng));
    ZONES.forEach((zone, zi) => {
      const lambda = (basePerDay * zone.weight * seasonProfile(zone, doy) * yf * dayNoise) / (weightSum * zoneNorm[zi]);
      const count = poisson(rng, lambda);
      for (let i = 0; i < count; i++) {
        const [dLon, dLat] = kmToDeg(zone.sigmaKm, zone.center[1]);
        const origin: Position = [zone.center[0] + normal(rng) * dLon, zone.center[1] + normal(rng) * dLat];
        const province = locate(origin);
        if (!province) continue;
        const intensity = Math.min(250, 0.15 / Math.pow(1 - rng(), 1 / 1.25));
        const duration = Math.max(1, Math.min(30, Math.round(1 + -Math.log(1 - rng()) * 1.2 + Math.log1p(intensity) * 1.6)));
        seeds.push({ start: d, origin, province, intensity, duration });
      }
    });
  }
  for (const [start, lon, lat, intensity, duration] of BIG_FIRES) {
    const d = daysBetween(FIRST_DATE, start);
    const province = locate([lon, lat]);
    if (d >= 0 && d < nDays && province) seeds.push({ start: d, origin: [lon, lat], province, intensity, duration });
  }
  seeds.sort((a, b) => a.start - b.start);

  const events: MockEvent[] = [];
  const eventDays: MockEventDay[] = [];
  const byDay: number[][] = Array.from({ length: nDays }, () => []);
  let nextId = 100000;

  for (const seed of seeds) {
    const eventIdx = events.length;
    const er = mulberry32(hashString(`event-${eventIdx}-${seed.start}`));
    const bearing = er() * 2 * Math.PI;
    const speedKm = 0.3 + Math.sqrt(seed.intensity) * 0.5;
    const days: number[] = [];
    let skippedInARow = 0;
    for (let k = 0; k < seed.duration; k++) {
      const day = seed.start + k;
      if (day >= nDays) break;
      const shape = Math.pow(Math.sin((Math.PI * (k + 0.5)) / seed.duration), 0.7);
      const intensity = seed.intensity * shape * Math.exp(0.4 * normal(er));
      const cloudy = k > 0 && k < seed.duration - 1 && skippedInARow < 2 && er() < 0.1;
      if (cloudy || nActive[day] === 0) {
        skippedInARow++;
        continue;
      }
      skippedInARow = 0;
      const [dLon, dLat] = kmToDeg(speedKm * k, seed.origin[1]);
      const center: Position = [seed.origin[0] + Math.cos(bearing) * dLon, seed.origin[1] + Math.sin(bearing) * dLat];
      const spreadKm = 0.3 + Math.sqrt(intensity) * 0.35;
      const ed: MockEventDay = {
        idx: eventDays.length,
        event: eventIdx,
        day,
        center,
        spreadKm,
        intensity,
        seed: hashString(`${eventIdx}:${k}`),
        idBase: nextId,
        bbox: [0, 0, 0, 0],
        all: emptyAgg(),
        high: emptyAgg(),
      };
      const date = toIso(t0 + day * DAY_MS);
      const points = generateHotspots(ed, date, nActive[day], false);
      if (points.length === 0) continue;
      const [bLon, bLat] = kmToDeg(spreadKm * 4, center[1]);
      ed.bbox = [center[0] - bLon, center[1] - bLat, center[0] + bLon, center[1] + bLat];
      for (const h of points) {
        addPoint(ed.all, h);
        if (h.confidence === "high") addPoint(ed.high, h);
      }
      nextId += points.length;
      eventDays.push(ed);
      byDay[day].push(ed.idx);
      days.push(ed.idx);
    }
    if (days.length === 0) continue;
    const startDate = toIso(t0 + eventDays[days[0]].day * DAY_MS);
    const startCell = latLngToCell(eventDays[days[0]].center[1], eventDays[days[0]].center[0], 8);
    const regionId = seed.province.properties.parent ?? seed.province.properties.country;
    events.push({
      idx: eventIdx,
      id: `e_${hex12(`${startDate}|${startCell}|${eventIdx}`)}`,
      origin: seed.origin,
      provinceId: seed.province.properties.id,
      regionId,
      countryId: seed.province.properties.country,
      days,
    });
  }

  return {
    firstDate: FIRST_DATE,
    lastDate,
    nDays,
    nActive,
    events,
    eventDays,
    byDay,
    eventById: new Map(events.map((e) => [e.id, e])),
    regions,
    regionById,
    locate,
  };
}
