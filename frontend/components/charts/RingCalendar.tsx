/** Ring calendar (spec §7.5): same values as the year heatmap, years as rings (oldest inside), months/weeks as angles. */
import { arc } from "d3-shape";
import { useMemo, useState } from "react";
import { periodColumns } from "../../lib/analysis";
import { useI18n } from "../../i18n/I18n";
import { HeatLegend } from "./HeatLegend";
import { cellLabel, statusText, useHeatmapScale, type HeatmapProps } from "./YearHeatmap";

const SIZE = 420;
const INNER = 46;
const OUTER = 186;

export function RingCalendar({ cells, mode, selectedDate, onSelect, formatValue, unitLabel, minYear, ariaLabel }: HeatmapProps) {
  const { t, f } = useI18n();
  const cols = periodColumns(mode);
  const years = useMemo(() => [...new Set(cells.map((c) => c.year))].sort((a, b) => a - b), [cells]);
  const { max, color } = useHeatmapScale(cells, minYear);
  const [hover, setHover] = useState<(typeof cells)[number] | null>(null);
  const ringW = (OUTER - INNER) / Math.max(1, years.length);
  const step = (2 * Math.PI) / cols;
  const path = arc<{ inner: number; outer: number; start: number; end: number }>()
    .innerRadius((d) => d.inner)
    .outerRadius((d) => d.outer)
    .startAngle((d) => d.start)
    .endAngle((d) => d.end)
    .padAngle(mode === "month" ? 0.004 : 0.001);
  const selected = cells.find((c) => selectedDate && c.start <= selectedDate && c.end >= selectedDate);
  const disabled = (c: (typeof cells)[number]) => c.status === "nodata" || (minYear !== undefined && c.year < minYear);

  return (
    <div className="ring">
      <svg viewBox={`${-SIZE / 2} ${-SIZE / 2} ${SIZE} ${SIZE}`} className="ring__svg" role="img" aria-label={ariaLabel}
        onMouseLeave={() => setHover(null)}>
        <defs>
          <pattern id="ring-hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="4" stroke="#57534e" strokeWidth="1" strokeOpacity="0.55" />
          </pattern>
        </defs>
        {cells.map((c) => {
          const ring = years.indexOf(c.year);
          const d = path({ inner: INNER + ring * ringW, outer: INNER + (ring + 1) * ringW, start: c.col * step, end: (c.col + 1) * step }) ?? "";
          const off = disabled(c);
          return (
            <g key={`${c.year}:${c.col}`} className={off ? "" : "heatmap__cell"} onMouseEnter={() => setHover(c)}
              onClick={() => !off && onSelect(c)}>
              <path d={d} fill={off ? "#ece9e4" : color(c.value ?? 0)} />
              {c.status === "incomplete" && !off && <path d={d} fill="url(#ring-hatch)" />}
              {c.status === "running" && <path d={d} fill="none" stroke="#1c1917" strokeDasharray="2 1" />}
            </g>
          );
        })}
        {selected && (
          <path className="heatmap__selected"
            d={path({
              inner: INNER + years.indexOf(selected.year) * ringW,
              outer: INNER + (years.indexOf(selected.year) + 1) * ringW,
              start: selected.col * step,
              end: (selected.col + 1) * step,
            }) ?? ""} />
        )}
        {Array.from({ length: 12 }, (_, m) => {
          const a = ((m + 0.5) / 12) * 2 * Math.PI;
          return (
            <text key={m} x={Math.sin(a) * (OUTER + 14)} y={-Math.cos(a) * (OUTER + 14) + 4} textAnchor="middle" className="heatmap__label">
              {f.monthShort(m + 1)}
            </text>
          );
        })}
        <text x={0} y={-4} textAnchor="middle" className="heatmap__label">{years[0]}</text>
        <text x={0} y={10} textAnchor="middle" className="heatmap__label">innen</text>
        <text x={4} y={-OUTER + ringW / 2 + 3} className="heatmap__label heatmap__label--strong">{years[years.length - 1]}</text>
      </svg>
      <p className="heatmap__readout" aria-live="polite">
        {hover
          ? `${cellLabel(hover, mode, f)}: ${hover.value === null || disabled(hover) ? "–" : `${formatValue(hover.value)} ${unitLabel}`}${statusText(hover.status, t)}`
          : t("heat.ringHint")}
      </p>
      <HeatLegend max={max} color={color} formatValue={formatValue} unitLabel={unitLabel} />
    </div>
  );
}
