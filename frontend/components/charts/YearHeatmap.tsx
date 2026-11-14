/**
 * Year heatmap (spec §7.5): rows = years, columns = months or weeks. Also used on page 1 as the calendar heatmap.
 * Keyboard: focus the chart, move with the arrow keys, Enter selects the cell.
 */
import { useMemo, useState, type KeyboardEvent } from "react";
import { periodColumns, type PeriodCell, type PeriodMode } from "../../lib/analysis";
import { sequentialScale } from "../../lib/colors";
import { formatDayMonth, monthShort } from "../../lib/dates";
import { HeatLegend } from "./HeatLegend";

export interface HeatmapProps {
  cells: PeriodCell[];
  mode: PeriodMode;
  selectedDate: string | null;
  onSelect: (cell: PeriodCell) => void;
  formatValue: (v: number) => string;
  unitLabel: string;
  /** years before this are greyed out (events are only comparable from 2012) */
  minYear?: number;
  ariaLabel: string;
}

const LABEL_W = 34;
const HEADER_H = 16;

export function cellLabel(c: PeriodCell, mode: PeriodMode): string {
  return mode === "month" ? `${monthShort(c.col + 1)} ${c.year}` : `${formatDayMonth(c.start)}–${formatDayMonth(c.end)}${c.year}`;
}

export const STATUS_TEXT: Record<PeriodCell["status"], string> = {
  complete: "",
  incomplete: " (unvollständig)",
  running: " (läuft noch)",
  nodata: " (keine Daten)",
};

export function useHeatmapScale(cells: PeriodCell[], minYear?: number) {
  return useMemo(() => {
    const max = Math.max(0, ...cells.filter((c) => c.status === "complete" && (!minYear || c.year >= minYear)).map((c) => c.value ?? 0));
    return { max, color: sequentialScale(max) };
  }, [cells, minYear]);
}

export function YearHeatmap({ cells, mode, selectedDate, onSelect, formatValue, unitLabel, minYear, ariaLabel }: HeatmapProps) {
  const cols = periodColumns(mode);
  const years = useMemo(() => [...new Set(cells.map((c) => c.year))].sort((a, b) => b - a), [cells]);
  const { max, color } = useHeatmapScale(cells, minYear);
  const byKey = useMemo(() => new Map(cells.map((c) => [`${c.year}:${c.col}`, c])), [cells]);
  const selected = cells.find((c) => selectedDate && c.start <= selectedDate && c.end >= selectedDate) ?? null;
  const [cursor, setCursor] = useState<{ year: number; col: number } | null>(null);
  const [hover, setHover] = useState<PeriodCell | null>(null);

  const cellW = mode === "month" ? 22 : 15;
  const cellH = years.length > 20 ? 9 : 12;
  const width = LABEL_W + cols * cellW;
  const height = HEADER_H + years.length * cellH;
  const active = cursor ? byKey.get(`${cursor.year}:${cursor.col}`) ?? null : null;
  const shown = hover ?? active;
  const disabled = (c: PeriodCell) => c.status === "nodata" || (minYear !== undefined && c.year < minYear);

  const onKey = (e: KeyboardEvent) => {
    const cur = cursor ?? (selected ? { year: selected.year, col: selected.col } : { year: years[0], col: 0 });
    let { year, col } = cur;
    if (e.key === "ArrowLeft") col = Math.max(0, col - 1);
    else if (e.key === "ArrowRight") col = Math.min(cols - 1, col + 1);
    else if (e.key === "ArrowUp") year = Math.min(years[0], year + 1);
    else if (e.key === "ArrowDown") year = Math.max(years[years.length - 1], year - 1);
    else if (e.key === "Enter" || e.key === " ") {
      const c = byKey.get(`${year}:${col}`);
      if (c && !disabled(c)) onSelect(c);
    } else return;
    e.preventDefault();
    setCursor({ year, col });
  };

  return (
    <div className="heatmap">
      <svg
        className="heatmap__svg"
        viewBox={`0 0 ${width} ${height}`}
        role="grid"
        aria-label={`${ariaLabel}. Pfeiltasten wählen ein Feld, Enter setzt den Stichtag.`}
        tabIndex={0}
        onKeyDown={onKey}
        onBlur={() => setCursor(null)}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="4" stroke="#57534e" strokeWidth="1" strokeOpacity="0.55" />
          </pattern>
        </defs>
        {Array.from({ length: cols }, (_, col) =>
          mode === "month" || col % 4 === 0 ? (
            <text key={col} x={LABEL_W + col * cellW + (mode === "month" ? cellW / 2 : 0)} y={11} className="heatmap__label"
              textAnchor={mode === "month" ? "middle" : "start"}>
              {mode === "month" ? monthShort(col + 1).slice(0, 1) : col + 1}
            </text>
          ) : null,
        )}
        {years.map((year, row) => (
          <g key={year} transform={`translate(0, ${HEADER_H + row * cellH})`}>
            <text x={LABEL_W - 4} y={cellH - 2} textAnchor="end" className="heatmap__label">
              {year % 5 === 0 || cellH >= 12 || (row === 0 && Math.min(year % 5, 5 - (year % 5)) >= 2) ? year : ""}
            </text>
            {Array.from({ length: cols }, (_, col) => {
              const c = byKey.get(`${year}:${col}`);
              if (!c) return null;
              const off = disabled(c);
              return (
                <g key={col} onMouseEnter={() => setHover(c)} onClick={() => !off && onSelect(c)} className={off ? "" : "heatmap__cell"}>
                  <rect x={LABEL_W + col * cellW + 0.5} y={0.5} width={cellW - 1} height={cellH - 1}
                    fill={off ? "#ece9e4" : color(c.value ?? 0)} />
                  {c.status === "incomplete" && !off && (
                    <rect x={LABEL_W + col * cellW + 0.5} y={0.5} width={cellW - 1} height={cellH - 1} fill="url(#hatch)" />
                  )}
                  {c.status === "running" && (
                    <rect x={LABEL_W + col * cellW + 1} y={1} width={cellW - 2} height={cellH - 2} fill="none"
                      stroke="#1c1917" strokeDasharray="2 1" strokeWidth={1} />
                  )}
                </g>
              );
            })}
          </g>
        ))}
        {selected && years.includes(selected.year) && (
          <rect className="heatmap__selected" x={LABEL_W + selected.col * cellW} y={HEADER_H + years.indexOf(selected.year) * cellH}
            width={cellW} height={cellH} />
        )}
        {active && (
          <rect className="heatmap__cursor" x={LABEL_W + active.col * cellW - 1} y={HEADER_H + years.indexOf(active.year) * cellH - 1}
            width={cellW + 2} height={cellH + 2} />
        )}
      </svg>
      <p className="heatmap__readout" aria-live="polite">
        {shown
          ? `${cellLabel(shown, mode)}: ${shown.value === null || disabled(shown) ? "–" : `${formatValue(shown.value)} ${unitLabel}`}${STATUS_TEXT[shown.status]}`
          : "Feld anklicken, um den Stichtag zu setzen."}
      </p>
      <HeatLegend max={max} color={sequentialScale(max)} formatValue={formatValue} unitLabel={unitLabel} />
    </div>
  );
}
