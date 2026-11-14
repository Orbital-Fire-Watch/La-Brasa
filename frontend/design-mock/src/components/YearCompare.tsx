/**
 * Year overview with raw MODIS / VIIRS detections: one heatmap per family (years × weeks or months) on one shared
 * colour scale, plus raw detections per year. Grey = no satellite of the family, hatched = incomplete (API limit).
 */
import { useId, useMemo } from "react";
import { periodCells, type PeriodCell, type PeriodMode } from "../../../lib/analysis";
import type { SensorDailyResult } from "../api/sensorDaily";
import { useI18n } from "../i18n/I18n";
import { valueScale } from "../palette";
import { usePrefs } from "../prefs";
import { FAMILY_COLOR, FAMILY_NAME, type SensorFamily } from "../sensors";

type RawCell = PeriodCell & { incomplete: boolean };

/** Every fifth year, plus the edge years unless they would collide with a neighbouring fifth year. */
const showYearLabel = (y: number, edge: boolean) => y % 5 === 0 || (edge && y % 5 >= 2 && y % 5 <= 3);

function familyCells(result: SensorDailyResult, fam: SensorFamily, mode: PeriodMode): RawCell[] {
  const { data } = result;
  const col = data.families[fam].detections;
  const series = { start: data.start, end: data.end, fires: col, hotspots: col, frp_sum: data.families[fam].frp_sum };
  const incomplete = data.incomplete ?? [];
  return periodCells(series, "fires", mode).map((c) => {
    // A period in which no satellite of the family flew has no data (not zero fires).
    const i0 = Math.max(0, Math.round((Date.parse(c.start) - Date.parse(data.start)) / 864e5));
    const i1 = Math.min(col.length - 1, Math.round((Date.parse(c.end) - Date.parse(data.start)) / 864e5));
    let any = false;
    for (let i = i0; i <= i1 && !any; i++) any = col[i] !== null;
    const overlaps = incomplete.some((w) => w.start <= c.end && w.end >= c.start);
    return any ? { ...c, incomplete: overlaps } : { ...c, value: null, status: "nodata", incomplete: false };
  });
}

interface HeatmapProps {
  family: SensorFamily;
  cells: RawCell[];
  mode: PeriodMode;
  color: (v: number) => string;
  selectedDate: string;
  onSelect: (end: string) => void;
  hatchId: string;
}

function RawHeatmap({ family, cells, mode, color, selectedDate, onSelect, hatchId }: HeatmapProps) {
  const { t, f } = useI18n();
  const years = useMemo(() => [...new Set(cells.map((c) => c.year))].sort((a, b) => b - a), [cells]);
  const cols = mode === "month" ? 12 : 52;
  const cw = mode === "month" ? 22 : 15;
  const ch = years.length > 20 ? 9 : 12;
  const LW = 34;
  const HH = 14;
  const label = (c: RawCell) =>
    mode === "month" ? `${f.monthShort(c.col + 1)} ${c.year}` : `${f.dayMonth(c.start)} – ${f.dayMonth(c.end)} ${c.year}`;
  return (
    <figure className="ow-yc__map">
      <figcaption className="ow-yc__caption">
        <span className="ow-swatch" style={{ background: FAMILY_COLOR[family] }} />
        {t(`cmp.mapLabel.${family}`)}
      </figcaption>
      <svg viewBox={`0 0 ${LW + cols * cw} ${HH + years.length * ch}`} role="img"
        aria-label={t(mode === "month" ? "year.heatAriaMonth" : "year.heatAriaWeek", { family: FAMILY_NAME[family] })}>
        {Array.from({ length: cols }, (_, i) => (mode === "month" || i % 4 === 0) && (
          <text key={i} x={LW + i * cw + cw / 2} y={10} textAnchor="middle" className="ow-yc__tick">
            {mode === "month" ? f.monthNarrow(i + 1) : i + 1}
          </text>
        ))}
        {years.map((y, r) => (
          <text key={y} x={0} y={HH + r * ch + ch - 2} className="ow-yc__tick">{showYearLabel(y, r === 0) ? y : ""}</text>
        ))}
        {cells.map((c) => {
          const r = years.indexOf(c.year);
          const x = LW + c.col * cw;
          const y = HH + r * ch;
          const selected = c.start <= selectedDate && c.end >= selectedDate;
          const text = c.status === "nodata"
            ? t("year.cellNoSatellite", { label: label(c) })
            : `${t("year.cellValue", { label: label(c), value: f.int(c.value ?? 0) })}${c.incomplete ? ` (${t("year.hatched")})` : c.status === "running" ? ` (${t("status.running")})` : ""}`;
          return (
            <g key={`${c.year}:${c.col}`} className="ow-yc__cell" onClick={() => c.status !== "nodata" && onSelect(c.end)}>
              <title>{text}</title>
              <rect x={x} y={y} width={cw - 1} height={ch - 1} rx={1}
                fill={c.status === "nodata" || c.value === null ? "var(--ow-yc-nodata)" : color(c.value)} />
              {c.incomplete && <rect x={x} y={y} width={cw - 1} height={ch - 1} fill={`url(#${hatchId})`} />}
              {c.status === "running" && <rect x={x + 0.5} y={y + 0.5} width={cw - 2} height={ch - 2} fill="none" className="ow-yc__running" />}
              {selected && <rect x={x - 0.5} y={y - 0.5} width={cw} height={ch} fill="none" className="ow-yc__selected" />}
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

function YearTotals({ data }: { data: SensorDailyResult["data"] }) {
  const { t, f } = useI18n();
  const totals = useMemo(() => {
    const out = new Map<number, { modis: number | null; viirs: number | null }>();
    for (const fam of ["modis", "viirs"] as const) {
      data.families[fam].detections.forEach((v, i) => {
        const y = Number(new Date(Date.parse(data.start) + i * 864e5).toISOString().slice(0, 4));
        const e = out.get(y) ?? { modis: null, viirs: null };
        if (v !== null) e[fam] = (e[fam] ?? 0) + v;
        out.set(y, e);
      });
    }
    return [...out.entries()].sort((a, b) => a[0] - b[0]);
  }, [data]);
  const max = Math.max(1, ...totals.flatMap(([, v]) => [v.modis ?? 0, v.viirs ?? 0]));
  const W = 640;
  const H = 120;
  const slot = W / Math.max(1, totals.length);
  const bar = Math.max(1, slot / 2 - 1.5);
  return (
    <figure className="ow-yc__totals">
      <figcaption className="ow-yc__caption">{t("year.totals")}</figcaption>
      <svg viewBox={`0 0 ${W} ${H + 16}`} role="img" aria-label={t("year.totalsAria")}>
        <line x1={0} x2={W} y1={H} y2={H} className="ow-cmp__axis" />
        {totals.map(([year, v], i) => (
          <g key={year}>
            <title>{t("year.totalTitle", { year: String(year), modis: v.modis === null ? "–" : f.int(v.modis), viirs: v.viirs === null ? "–" : f.int(v.viirs) })}</title>
            {v.modis !== null && <rect x={i * slot + 1} y={H - (H * v.modis) / max} width={bar} height={(H * v.modis) / max} fill={FAMILY_COLOR.modis} />}
            {v.viirs !== null && <rect x={i * slot + 1 + bar} y={H - (H * v.viirs) / max} width={bar} height={(H * v.viirs) / max} fill={FAMILY_COLOR.viirs} />}
            {showYearLabel(year, i === 0 || i === totals.length - 1) && (
              <text x={i * slot + slot / 2} y={H + 12} textAnchor="middle" className="ow-yc__tick">{year}</text>
            )}
          </g>
        ))}
      </svg>
    </figure>
  );
}

export function YearCompare({ result, view, mode, selectedDate, onSelect }: {
  result: SensorDailyResult; view: "modis" | "viirs" | "compare"; mode: PeriodMode; selectedDate: string; onSelect: (end: string) => void;
}) {
  const { t, f } = useI18n();
  const { prefs } = usePrefs();
  const hatchId = useId().replace(/:/g, "");
  const families: SensorFamily[] = view === "compare" ? ["modis", "viirs"] : [view];
  const cells = useMemo(() => {
    const shown: SensorFamily[] = view === "compare" ? ["modis", "viirs"] : [view];
    return Object.fromEntries(shown.map((fam) => [fam, familyCells(result, fam, mode)])) as Record<SensorFamily, RawCell[]>;
  }, [result, mode, view]);
  // One shared scale over all shown families and complete periods, so the same colour means the same number.
  const max = Math.max(1, ...families.flatMap((fam) => cells[fam].filter((c) => c.status === "complete" && !c.incomplete).map((c) => c.value ?? 0)));
  const color = valueScale(prefs.palette, max);
  const incompleteCount = (result.data.incomplete ?? []).length;

  return (
    <div className="ow-yc">
      <svg width="0" height="0" aria-hidden="true" style={{ position: "absolute" }}>
        <defs>
          <pattern id={hatchId} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="4" className="ow-yc__hatch" strokeWidth="1.5" />
          </pattern>
        </defs>
      </svg>
      <div className={view === "compare" ? "ow-yc__pair" : undefined}>
        {families.map((fam) => (
          <RawHeatmap key={fam} family={fam} cells={cells[fam]} mode={mode} color={color} selectedDate={selectedDate} onSelect={onSelect} hatchId={hatchId} />
        ))}
      </div>
      <div className="ow-yc__legend">
          <div className="ow-ramp">
            <span>0</span>
            <span className="ow-ramp__bar" style={{ background: `linear-gradient(to right, ${[0, 0.1, 0.3, 0.6, 1].map((v) => color(max * v * v)).join(", ")})` }} />
            <span>{f.int(max)} {t("cmp.detections")}{view === "compare" ? `, ${t("year.sharedScale")}` : ""}</span>
          </div>
          <span className="ow-yc__key"><span className="ow-yc__swatch ow-yc__swatch--nodata" />{t("year.grey")}</span>
          <span className="ow-yc__key"><span className="ow-yc__swatch ow-yc__swatch--hatch" />{t("year.hatched")}</span>
          <span className="ow-yc__key"><span className="ow-yc__swatch ow-yc__swatch--running" />{t("status.running")}</span>
      </div>
      {view === "compare" && <YearTotals data={result.data} />}
      <p className="ow-small ow-muted">
        {result.source === "endpoint" ? t("year.sourceEndpoint") : t("year.sourceHotspots", { count: result.requests })}
        {" "}{t("cmp.caveat")}
      </p>
      {incompleteCount > 0 && <p className="ow-cmp__warning" role="note">{t("year.incomplete", { count: incompleteCount })}</p>}
    </div>
  );
}
