/** Small geometry helpers (WGS84, [lon, lat]) so the app does not need a full GIS library. */

export type Position = [number, number];
export type BBox = [number, number, number, number];
export type Ring = Position[];
export interface PolygonGeometry {
  type: "Polygon";
  coordinates: Ring[];
}
export interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: Ring[][];
}
export type AreaGeometry = PolygonGeometry | MultiPolygonGeometry;

const EARTH_RADIUS_KM = 6371.0088;
const RAD = Math.PI / 180;

export const round4 = (v: number): number => Math.round(v * 1e4) / 1e4;
export const roundPosition = ([x, y]: Position): Position => [round4(x), round4(y)];

export function polygonsOf(g: AreaGeometry): Ring[][] {
  return g.type === "Polygon" ? [g.coordinates] : g.coordinates;
}

/** Shoelace area (in degrees²) – positive for counter-clockwise rings. */
export function ringSignedArea(ring: Ring): number {
  let a = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) a += (ring[j][0] - ring[i][0]) * (ring[j][1] + ring[i][1]);
  return a / 2;
}

/** Returns the ring with the requested winding (RFC 7946: outer rings counter-clockwise, holes clockwise). */
export function orientRing(ring: Ring, ccw: boolean): Ring {
  return ringSignedArea(ring) > 0 === ccw ? ring : [...ring].reverse();
}

const WORLD_RING: Ring = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];

/**
 * The whole world with the outer rings of `geometries` cut out – a fill on top darkens everything outside them.
 * Holes are wound clockwise explicitly, MapLibre tells holes from new polygons by winding.
 */
export function worldWithout(geometries: AreaGeometry[]): PolygonGeometry {
  const holes = geometries.flatMap((g) => polygonsOf(g).map((p) => orientRing(closeRing(p[0]), false)));
  return { type: "Polygon", coordinates: [WORLD_RING, ...holes] };
}

export function countVertices(g: AreaGeometry): number {
  return polygonsOf(g).reduce((n, p) => n + p.reduce((m, r) => m + r.length, 0), 0);
}

export function closeRing(ring: Ring): Ring {
  if (ring.length === 0) return ring;
  const [fx, fy] = ring[0];
  const [lx, ly] = ring[ring.length - 1];
  return fx === lx && fy === ly ? ring : [...ring, ring[0]];
}

export function bboxOf(g: AreaGeometry): BBox {
  let b: BBox = [Infinity, Infinity, -Infinity, -Infinity];
  for (const poly of polygonsOf(g)) for (const [x, y] of poly[0]) b = extend(b, x, y);
  return b;
}

export function bboxOfPoints(points: Position[]): BBox {
  let b: BBox = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y] of points) b = extend(b, x, y);
  return b;
}

function extend(b: BBox, x: number, y: number): BBox {
  return [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)];
}

export const pointInBbox = ([x, y]: Position, b: BBox): boolean => x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3];

export const bboxIntersects = (a: BBox, b: BBox): boolean => a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];

function pointInRing([x, y]: Position, ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Point in polygon with holes, for Polygon and MultiPolygon. */
export function pointInGeometry(p: Position, g: AreaGeometry): boolean {
  return polygonsOf(g).some(([outer, ...holes]) => pointInRing(p, outer) && !holes.some((h) => pointInRing(p, h)));
}

/** Great-circle distance in km. */
export function distanceKm([x1, y1]: Position, [x2, y2]: Position): number {
  const dLat = (y2 - y1) * RAD;
  const dLon = (x2 - x1) * RAD;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(y1 * RAD) * Math.cos(y2 * RAD) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

function destination([lon, lat]: Position, distKm: number, bearingDeg: number): Position {
  const d = distKm / EARTH_RADIUS_KM;
  const b = bearingDeg * RAD;
  const p1 = lat * RAD;
  const l1 = lon * RAD;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
  const l2 = l1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [l2 / RAD, p2 / RAD];
}

/** Geodesic circle as polygon (like turf.circle with `steps`). */
export function circlePolygon(center: Position, radiusKm: number, steps = 64): PolygonGeometry {
  const ring: Ring = [];
  for (let i = 0; i < steps; i++) ring.push(roundPosition(destination(center, radiusKm, (-360 * i) / steps)));
  return { type: "Polygon", coordinates: [closeRing(ring)] };
}

export function rectanglePolygon(a: Position, b: Position): PolygonGeometry {
  const [x0, x1] = [Math.min(a[0], b[0]), Math.max(a[0], b[0])].map(round4);
  const [y0, y1] = [Math.min(a[1], b[1]), Math.max(a[1], b[1])].map(round4);
  return { type: "Polygon", coordinates: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]] };
}

export function bboxPolygon(b: BBox): PolygonGeometry {
  return rectanglePolygon([b[0], b[1]], [b[2], b[3]]);
}

function sqSegmentDistance(p: Position, a: Position, b: Position): number {
  let [x, y] = a;
  let dx = b[0] - x;
  let dy = b[1] - y;
  if (dx !== 0 || dy !== 0) {
    const t = Math.max(0, Math.min(1, ((p[0] - x) * dx + (p[1] - y) * dy) / (dx * dx + dy * dy)));
    x += dx * t;
    y += dy * t;
  }
  dx = p[0] - x;
  dy = p[1] - y;
  return dx * dx + dy * dy;
}

/** Douglas–Peucker simplification of a closed ring (tolerance in degrees). */
export function simplifyRing(ring: Ring, toleranceDeg: number): Ring {
  if (ring.length <= 4) return ring;
  const sq = toleranceDeg * toleranceDeg;
  const keep = new Uint8Array(ring.length);
  keep[0] = keep[ring.length - 1] = 1;
  const stack: [number, number][] = [[0, ring.length - 1]];
  while (stack.length) {
    const [first, last] = stack.pop() as [number, number];
    let maxD = 0;
    let idx = -1;
    for (let i = first + 1; i < last; i++) {
      const d = sqSegmentDistance(ring[i], ring[first], ring[last]);
      if (d > maxD) {
        maxD = d;
        idx = i;
      }
    }
    if (maxD > sq) {
      keep[idx] = 1;
      stack.push([first, idx], [idx, last]);
    }
  }
  const out = ring.filter((_, i) => keep[i] === 1);
  return out.length >= 4 ? out : ring;
}

/**
 * Simplifies a freehand ring until it has at most `maxVertices` points (spec §6.3: turf.simplify
 * with tolerance 0.001–0.01°). Starts with the smallest tolerance so the shape stays as close as possible.
 */
export function simplifyToMaxVertices(ring: Ring, maxVertices: number): Ring {
  let out = closeRing(ring.map(roundPosition));
  for (let tol = 0.0005; out.length > maxVertices && tol < 1; tol *= 1.6) out = simplifyRing(out, tol);
  return out;
}

/** Spherical polygon area in km² (same approach as turf.area). */
function ringAreaKm2(ring: Ring): number {
  let total = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[i + 1];
    total += (x2 - x1) * RAD * (2 + Math.sin(y1 * RAD) + Math.sin(y2 * RAD));
  }
  return Math.abs((total * EARTH_RADIUS_KM * EARTH_RADIUS_KM) / 2);
}

export function geometryAreaKm2(g: AreaGeometry): number {
  return polygonsOf(g).reduce(
    (sum, [outer, ...holes]) => sum + ringAreaKm2(outer) - holes.reduce((h, r) => h + ringAreaKm2(r), 0),
    0,
  );
}

export function toMultiPolygon(g: AreaGeometry): MultiPolygonGeometry {
  return g.type === "MultiPolygon" ? g : { type: "MultiPolygon", coordinates: [g.coordinates] };
}

/** Parses "lon, lat" / "lon lat" pairs, one per line (or separated by ";"). Returns null on bad input. */
export function parseCoordinateList(text: string): Position[] | null {
  const parts = text
    .split(/[\n;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const out: Position[] = [];
  for (const part of parts) {
    const nums = part.split(/[\s,]+/).filter(Boolean).map(Number);
    if (nums.length !== 2 || nums.some((n) => !Number.isFinite(n))) return null;
    const [lon, lat] = nums;
    if (lon < -180 || lon > 180 || lat < -90 || lat > 90) return null;
    out.push([lon, lat]);
  }
  return out;
}
