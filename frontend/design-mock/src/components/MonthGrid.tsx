/**
 * Calendar heatmap of the start page: years as rows, months as columns. Clicking a month sets the reference date.
 * Keyboard: one cell is in the tab order, arrow keys move between cells, Enter/Space selects.
 */
import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { PeriodCell } from "../../../lib/analysis";
import { useI18n } from "../i18n/I18n";
import { valueScale } from "../palette";
import { usePrefs } from "../prefs";

interface MonthGridProps {
  cells: PeriodCell[];
  selectedDate: string;
  onSelect: (cell: PeriodCell) => void;
  formatValue: (v: number) => string;
  unit: string;
  minYear?: number;
}

const STEPS: Record<string, [number, number]> = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] };

export function MonthGrid({ cells, selectedDate, onSelect, formatValue, unit, minYear }: MonthGridProps) {
  const { prefs } = usePrefs();
  const { t, f } = useI18n();
  const years = useMemo(() => [...new Set(cells.map((c) => c.year))].sort((a, b) => b - a), [cells]);
  const byKey = useMemo(() => new Map(cells.map((c) => [`${c.year}:${c.col}`, c])), [cells]);
  const max = useMemo(
    () => Math.max(0, ...cells.filter((c) => c.status === "complete" && (!minYear || c.year >= minYear)).map((c) => c.value ?? 0)),
    [cells, minYear],
  );
  const color = valueScale(prefs.palette, max);
  const selected = cells.find((c) => c.start <= selectedDate && c.end >= selectedDate) ?? null;
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [hover, setHover] = useState<PeriodCell | null>(null);
  const grid = useRef<HTMLDivElement>(null);

  const tabKey = focusKey ?? (selected ? `${selected.year}:${selected.col}` : years.length ? `${years[0]}:0` : null);
  const usable = (c: PeriodCell) => c.status !== "nodata" && !(minYear !== undefined && c.year < minYear);
  const status = (c: PeriodCell) => (c.status === "complete" ? "" : ` (${t(`status.${c.status}`)})`);
  const valueText = (c: PeriodCell) => (c.value === null ? t("status.nodata") : `${formatValue(c.value)} ${unit}`);

  const move = (e: KeyboardEvent<HTMLButtonElement>, c: PeriodCell) => {
    const step = STEPS[e.key];
    if (!step) return;
    e.preventDefault();
    const y = years.indexOf(c.year) + step[0];
    const col = c.col + step[1];
    if (y < 0 || y >= years.length || col < 0 || col > 11) return;
    const key = `${years[y]}:${col}`;
    setFocusKey(key);
    grid.current?.querySelector<HTMLButtonElement>(`[data-key="${key}"]`)?.focus();
  };

  const shown = hover ?? selected;
  return (
    <div className="ow-monthgrid">
      <div className="ow-monthgrid__grid" ref={grid} role="grid" aria-label={t("cal.aria")}>
        <div className="ow-monthgrid__row ow-monthgrid__row--head" role="row">
          <span role="columnheader" />
          {Array.from({ length: 12 }, (_, i) => (
            <span key={i} role="columnheader" className="ow-monthgrid__month" title={f.monthLong(i + 1)}>{f.monthNarrow(i + 1)}</span>
          ))}
        </div>
        {years.map((y) => (
          <div key={y} className="ow-monthgrid__row" role="row">
            <span role="rowheader" className="ow-monthgrid__year">{y}</span>
            {Array.from({ length: 12 }, (_, col) => {
              const c = byKey.get(`${y}:${col}`);
              const key = `${y}:${col}`;
              if (!c) return <span key={col} role="gridcell" className="ow-monthgrid__cell" data-empty />;
              const ok = usable(c);
              return (
                <button key={col} type="button" role="gridcell" data-key={key} className="ow-monthgrid__cell"
                  aria-selected={selected?.year === y && selected.col === col} disabled={!ok} tabIndex={key === tabKey ? 0 : -1}
                  style={ok && c.value !== null ? { background: color(c.value) } : undefined}
                  data-running={c.status === "running" || undefined}
                  aria-label={`${f.monthLong(col + 1)} ${y}: ${valueText(c)}${status(c)}`}
                  onClick={() => onSelect(c)} onKeyDown={(e) => move(e, c)}
                  onMouseEnter={() => setHover(c)} onMouseLeave={() => setHover(null)} onFocus={() => setFocusKey(key)} />
              );
            })}
          </div>
        ))}
      </div>
      <p className="ow-monthgrid__readout" aria-live="polite">
        {shown ? (
          <>
            <strong>{f.monthLong(shown.col + 1)} {shown.year}</strong> {valueText(shown)}
            <span className="ow-muted">{status(shown)}</span>
          </>
        ) : " "}
      </p>
      <div className="ow-ramp" aria-hidden="true">
        <span>0</span>
        <span className="ow-ramp__bar" style={{ background: `linear-gradient(to right, ${[0, 0.25, 0.5, 0.75, 1].map((s) => color(max * s * s)).join(", ")})` }} />
        <span>{formatValue(max)} {unit}</span>
      </div>
    </div>
  );
}
