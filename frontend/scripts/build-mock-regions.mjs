/**
 * Builds public/mock/regions.json – the mock answer of GET /api/regions (spec §6.2).
 *
 * Source: Eurostat GISCO NUTS 2021 (1:10M), © EuroGeographics for the administrative boundaries.
 * Spanish NUTS codes are mapped to ISO 3166-2 as the spec asks. Portuguese provinces use the
 * NUTS-3 sub-regions (the distritos are not part of NUTS); the real backend replaces all of this.
 *
 * Usage: node scripts/build-mock-regions.mjs [dir-with-NUTS-geojson-files]
 * Without a directory the files are downloaded from GISCO.
 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";

const GISCO = "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson";
const TOLERANCE_DEG = 0.005;
const OUT = path.join(path.dirname(new URL(import.meta.url).pathname), "..", "public", "mock", "regions.json");

const ES_REGIONS = {
  ES11: "ES-GA", ES12: "ES-AS", ES13: "ES-CB", ES21: "ES-PV", ES22: "ES-NC", ES23: "ES-RI",
  ES24: "ES-AR", ES30: "ES-MD", ES41: "ES-CL", ES42: "ES-CM", ES43: "ES-EX", ES51: "ES-CT",
  ES52: "ES-VC", ES53: "ES-IB", ES61: "ES-AN", ES62: "ES-MC",
};
const ES_PROVINCES = {
  ES111: "ES-C", ES112: "ES-LU", ES113: "ES-OR", ES114: "ES-PO", ES120: "ES-O", ES130: "ES-S",
  ES211: "ES-VI", ES212: "ES-SS", ES213: "ES-BI", ES220: "ES-NA", ES230: "ES-LO", ES241: "ES-HU",
  ES242: "ES-TE", ES243: "ES-Z", ES300: "ES-M", ES411: "ES-AV", ES412: "ES-BU", ES413: "ES-LE",
  ES414: "ES-P", ES415: "ES-SA", ES416: "ES-SG", ES417: "ES-SO", ES418: "ES-VA", ES419: "ES-ZA",
  ES421: "ES-AB", ES422: "ES-CR", ES423: "ES-CU", ES424: "ES-GU", ES425: "ES-TO", ES431: "ES-BA",
  ES432: "ES-CC", ES511: "ES-B", ES512: "ES-GI", ES513: "ES-L", ES514: "ES-T", ES521: "ES-A",
  ES522: "ES-CS", ES523: "ES-V", ES531: "ES-PM", ES532: "ES-PM", ES533: "ES-PM", ES611: "ES-AL",
  ES612: "ES-CA", ES613: "ES-CO", ES614: "ES-GR", ES615: "ES-H", ES616: "ES-J", ES617: "ES-MA",
  ES618: "ES-SE", ES620: "ES-MU",
};
const NAME_OVERRIDES = { "ES-PM": "Illes Balears (provincia)", ES: "España", PT: "Portugal" };
const EXCLUDED = /^(ES63|ES64|ES70|PT20|PT30)/; // Ceuta, Melilla, Canarias, Açores, Madeira

async function load(dir, level) {
  const name = `NUTS_RG_10M_2021_4326_LEVL_${level}.geojson`;
  if (dir) return JSON.parse(await readFile(path.join(dir, name), "utf8"));
  const res = await fetch(`${GISCO}/${name}`);
  if (!res.ok) throw new Error(`GISCO ${name}: HTTP ${res.status}`);
  return res.json();
}

function sqSegDist(p, a, b) {
  let [x, y] = a;
  let dx = b[0] - x, dy = b[1] - y;
  if (dx !== 0 || dy !== 0) {
    const t = Math.max(0, Math.min(1, ((p[0] - x) * dx + (p[1] - y) * dy) / (dx * dx + dy * dy)));
    x += dx * t; y += dy * t;
  }
  dx = p[0] - x; dy = p[1] - y;
  return dx * dx + dy * dy;
}

function simplifyRing(ring, tol) {
  const sq = tol * tol;
  const keep = new Uint8Array(ring.length);
  keep[0] = keep[ring.length - 1] = 1;
  const stack = [[0, ring.length - 1]];
  while (stack.length) {
    const [first, last] = stack.pop();
    let maxD = 0, idx = -1;
    for (let i = first + 1; i < last; i++) {
      const d = sqSegDist(ring[i], ring[first], ring[last]);
      if (d > maxD) { maxD = d; idx = i; }
    }
    if (maxD > sq) { keep[idx] = 1; stack.push([first, idx], [idx, last]); }
  }
  const out = ring.filter((_, i) => keep[i]).map(([x, y]) => [Math.round(x * 1e4) / 1e4, Math.round(y * 1e4) / 1e4]);
  return out.length >= 4 ? out : null;
}

function polygons(geometry) {
  return geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
}

function simplifyPolygons(polys) {
  return polys
    .map((p) => p.map((r) => simplifyRing(r, TOLERANCE_DEG)).filter(Boolean))
    .filter((p) => p.length > 0);
}

/** Drops overseas parts from the country outlines: keep mainland + Balearics only. */
function isMainland(poly) {
  const [lon, lat] = poly[0][0];
  return lat > 36.0 && lon > -10.0;
}

function bbox(polys) {
  let b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const p of polys) for (const [x, y] of p[0]) b = [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)];
  return b.map((v) => Math.round(v * 1e4) / 1e4);
}

function feature(id, name, level, country, parent, polys) {
  return {
    type: "Feature",
    geometry: { type: "MultiPolygon", coordinates: polys },
    properties: { id, name: NAME_OVERRIDES[id] ?? name, level, country, parent, bbox: bbox(polys) },
  };
}

const dir = process.argv[2];
const [l0, l2, l3] = await Promise.all([load(dir, 0), load(dir, 2), load(dir, 3)]);
const inScope = (f) => ["ES", "PT"].includes(f.properties.CNTR_CODE) && !EXCLUDED.test(f.properties.NUTS_ID);
const features = [];

for (const f of l0.features.filter((f) => ["ES", "PT"].includes(f.properties.CNTR_CODE))) {
  const id = f.properties.CNTR_CODE;
  features.push(feature(id, f.properties.NUTS_NAME, "country", id, null, simplifyPolygons(polygons(f.geometry).filter(isMainland))));
}

for (const f of l2.features.filter(inScope)) {
  const nuts = f.properties.NUTS_ID, country = f.properties.CNTR_CODE;
  const id = country === "ES" ? ES_REGIONS[nuts] : nuts;
  features.push(feature(id, f.properties.NUTS_NAME, "region", country, country, simplifyPolygons(polygons(f.geometry))));
}

const provinces = new Map();
for (const f of l3.features.filter(inScope)) {
  const nuts = f.properties.NUTS_ID, country = f.properties.CNTR_CODE;
  const id = country === "ES" ? ES_PROVINCES[nuts] : nuts;
  const parent = country === "ES" ? ES_REGIONS[nuts.slice(0, 4)] : nuts.slice(0, 4);
  const entry = provinces.get(id) ?? { name: f.properties.NUTS_NAME, country, parent, polys: [] };
  entry.polys.push(...simplifyPolygons(polygons(f.geometry)));
  provinces.set(id, entry);
}
for (const [id, p] of provinces) features.push(feature(id, p.name, "province", p.country, p.parent, p.polys));

await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, JSON.stringify({ type: "FeatureCollection", features }));
console.log(`wrote ${features.length} features to ${OUT}`);
