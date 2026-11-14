/** Details of the selected event (GET /api/events/{id}) or H3 cell, with a small daily trend chart. */
import { formatDate } from "../../lib/dates";
import type { FireUnit } from "../../lib/fireUnits";
import { formatCompact, formatInt, formatKm2, formatOne } from "../../lib/format";
import type { EventDay, EventDetailResponse } from "../../services/api/types";
import { ErrorBlock, LoadingBlock } from "../ui/Status";

const SENSOR_SHORT: Record<string, string> = {
  MODIS_TERRA: "Terra", MODIS_AQUA: "Aqua", VIIRS_SNPP: "SNPP", VIIRS_NOAA20: "NOAA-20", VIIRS_NOAA21: "NOAA-21",
};
const TREND_TEXT = { growing: "wächst", stable: "stabil", shrinking: "nimmt ab" } as const;

function DailyBars({ days, metric }: { days: EventDay[]; metric: "fires" | "frp_sum" }) {
  const max = Math.max(1e-9, ...days.map((d) => d[metric]));
  const w = 100 / Math.max(1, days.length);
  return (
    <figure className="detail__chart">
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" role="img"
        aria-label={`Tagesverlauf ${metric === "fires" ? "Hotspots (harmonisiert)" : "FRP-Summe"}: ${days.map((d) => `${d.date.slice(5)} ${formatOne(d[metric])}`).join(", ")}`}>
        {days.map((d, i) => (
          <rect key={d.date} x={i * w + w * 0.1} width={w * 0.8} y={40 - (38 * d[metric]) / max} height={(38 * d[metric]) / max}
            fill={d.hotspots === 0 ? "#d6d3d1" : "#e8590c"} />
        ))}
      </svg>
      <figcaption className="small muted">
        {metric === "fires" ? "Hotspots (harmonisiert)" : "FRP-Summe"} pro Tag, {formatDate(days[0].date)} – {formatDate(days[days.length - 1].date)}
      </figcaption>
    </figure>
  );
}

interface UnitDetailProps {
  unit: FireUnit;
  name: string;
  detail: { status: "idle" | "loading" | "error" | "success"; data?: EventDetailResponse; error?: unknown; reload: () => void } | null;
  metric: "fires" | "frp_sum";
  onClose: () => void;
  onZoom: () => void;
}

export function UnitDetail({ unit, name, detail, metric, onClose, onZoom }: UnitDetailProps) {
  const p = detail?.data?.properties;
  return (
    <section className="detail" aria-labelledby="detail-title">
      <div className="detail__head">
        <h3 id="detail-title" className="detail__title">{name}</h3>
        <button type="button" className="btn btn--small" onClick={onZoom}>Zoomen</button>
        <button type="button" className="btn btn--small btn--ghost" onClick={onClose} aria-label="Details schließen">✕</button>
      </div>
      <dl className="facts">
        <div><dt>Zeitraum</dt><dd>{formatDate(unit.first_seen)} – {formatDate(unit.last_seen)} ({unit.duration_days} {unit.duration_days === 1 ? "Tag" : "Tage"})</dd></div>
        <div><dt>FRP-Summe (harm.)</dt><dd>{formatCompact(unit.frp_sum)} MW</dd></div>
        {p?.frp_max != null && <div><dt>Höchste FRP (Punkt)</dt><dd>{formatOne(p.frp_max)} MW</dd></div>}
        <div><dt>Hotspots</dt><dd>{formatInt(unit.hotspots)} roh · {formatOne(unit.fires)} harmonisiert</dd></div>
        {unit.area_km2 !== null && <div><dt>Betroffene Fläche (ca.)</dt><dd>{formatKm2(unit.area_km2)}{p ? ` · ${p.cells} Zellen` : ""}</dd></div>}
        {p && <div><dt>Sensoren</dt><dd>{p.sensors.map((s) => SENSOR_SHORT[s] ?? s).join(", ")}</dd></div>}
        {p?.trend && <div><dt>Trend</dt><dd>{TREND_TEXT[p.trend]} (3 Tage gegen 3 Tage davor)</dd></div>}
        {p?.landcover && <div><dt>Landbedeckung</dt><dd>{p.landcover.label}</dd></div>}
      </dl>
      {unit.area_km2 !== null && <p className="small muted">Fläche ist eine Schätzung aus H3-Zellen, keine kartierte Brandfläche.</p>}
      {detail?.status === "loading" && <LoadingBlock label="Tagesverlauf wird geladen …" />}
      {detail?.status === "error" && <ErrorBlock error={detail.error} onRetry={detail.reload} />}
      {detail?.data && detail.data.daily.length > 0 && <DailyBars days={detail.data.daily} metric={metric} />}
    </section>
  );
}
