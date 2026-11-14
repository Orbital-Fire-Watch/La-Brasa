/**
 * Time slider for D in D₀ ± 60 days (spec §4/§7.1). Moving it only changes the URL; daily-based views
 * update at once, server requests are debounced by the page. The bars show the daily metric for orientation.
 */
import { useMemo } from "react";
import { addDays, daysBetween, formatDate, formatDayMonth } from "../../lib/dates";
import type { Values } from "../../lib/analysis";

interface TimeSliderProps {
  value: string;
  anchor: string;
  min: string;
  max: string;
  onChange: (date: string) => void;
  /** daily values from min to max (same length as the range), null = no data */
  bars: Values | null;
  barsLabel: string;
}

export function TimeSlider({ value, anchor, min, max, onChange, bars, barsLabel }: TimeSliderProps) {
  const total = daysBetween(min, max);
  const pos = daysBetween(min, value);
  const anchorPos = daysBetween(min, anchor);
  const barMax = useMemo(() => Math.max(1e-9, ...(bars ?? []).map((v) => v ?? 0)), [bars]);
  const diff = daysBetween(anchor, value);
  const pct = (i: number) => (total === 0 ? 0 : (i / total) * 100);

  return (
    <div className="slider">
      <div className="slider__head">
        <button type="button" className="btn btn--small" onClick={() => onChange(addDays(value, -1))} disabled={value <= min}
          aria-label="Einen Tag zurück">◀</button>
        <output className="slider__value" aria-live="polite">
          {formatDate(value)}
          <span className="muted">{diff === 0 ? " · gewählter Stichtag" : ` · Stichtag ${diff > 0 ? "+" : "−"}${Math.abs(diff)} Tage`}</span>
        </output>
        <button type="button" className="btn btn--small" onClick={() => onChange(addDays(value, 1))} disabled={value >= max}
          aria-label="Einen Tag vor">▶</button>
        {diff !== 0 && (
          <button type="button" className="btn btn--small" onClick={() => onChange(anchor)}>Zurück zum Stichtag</button>
        )}
      </div>
      {bars && (
        <svg className="slider__bars" viewBox={`0 0 ${Math.max(1, total + 1)} 30`} preserveAspectRatio="none" role="img"
          aria-label={`Verlauf ${barsLabel} im Bereich des Zeitschiebers`}>
          {bars.map((v, i) =>
            v === null ? (
              <rect key={i} x={i} y={27} width={0.9} height={3} fill="#d6d3d1" />
            ) : (
              <rect key={i} x={i} y={30 - (28 * v) / barMax} width={0.9} height={(28 * v) / barMax}
                fill={i === pos ? "#d9480f" : "#a8a29e"} />
            ),
          )}
        </svg>
      )}
      <div className="slider__track">
        <span className="slider__anchor" style={{ left: `${pct(anchorPos)}%` }} aria-hidden="true" />
        <input type="range" min={0} max={total} step={1} value={pos} className="slider__input"
          aria-label="Zeitschieber: Stichtag" aria-valuetext={formatDate(value)}
          onChange={(e) => onChange(addDays(min, Number(e.target.value)))} />
      </div>
      <div className="slider__scale" aria-hidden="true">
        <span>{formatDayMonth(min)}</span>
        <span>{formatDayMonth(anchor)} (Stichtag)</span>
        <span>{formatDayMonth(max)}</span>
      </div>
    </div>
  );
}
