#!/usr/bin/env node
/**
 * Builds services/mock/forecastSample.json from a real forecast run (data/forecast/csv/forecast_daily.csv), only the
 * ES and PT regions. Dates are stored as lead days; the mock places them after its own last day.
 *     node scripts/build-mock-forecast.mjs
 */
import { readFileSync, writeFileSync } from "node:fs";

const src = new URL("../../data/forecast/csv/forecast_daily.csv", import.meta.url);
const out = new URL("../services/mock/forecastSample.json", import.meta.url);
const [head, ...lines] = readFileSync(src, "utf8").trim().split("\n");
const cols = head.split(",");
const NUM = ["lead_days", "p_big_fire_day", "p_big_fire_day_lo", "p_big_fire_day_hi", "p_fire_day", "p_clim_big_fire_day",
  "p_clim_fire_day", "risk_ratio"];
const round = (v) => Number(Number(v).toPrecision(4));
const rows = lines.map((l) => Object.fromEntries(l.split(",").map((v, i) => [cols[i], v])))
  .filter((r) => r.region_id.startsWith("ES") || r.region_id.startsWith("PT"))
  .map((r) => {
    const o = { region_id: r.region_id, risk_class: r.risk_class, source: r.source, model_version: r.model_version };
    for (const k of NUM) o[k] = k === "lead_days" ? Number(r[k]) : round(r[k]);
    return o;
  });
writeFileSync(out, JSON.stringify({ issue_date: rows.length ? lines[0].split(",")[1] : null, rows }) + "\n");
console.log(`${rows.length} rows -> ${out.pathname}`);
