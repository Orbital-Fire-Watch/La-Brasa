/**
 * Season curve (spec §7.4): metric per day over the calendar year, smoothed over 7 days.
 * Selected year highlighted, comparison years freely selectable, p25–p75 band and median of all years behind.
 * The point marks the reference day D and moves with the time slider (no request).
 */
import { scaleLinear } from "d3-scale";
import { area as d3area, line as d3line } from "d3-shape";
import { useMemo, useState, type MouseEvent } from "react";
import {
  climatology, movingAverage, yearSeries, yearTotals, type DailySeries, type SeriesKey, type Values,
} from "../../lib/analysis";
import { COMPARE_COLORS, SELECTED_LINE_COLOR } from "../../lib/colors";
import { dateFromDayOfYear, dayOfYear, yearOf } from "../../lib/dates";
import { useI18n } from "../../i18n/I18n";

const W = 900;
const H = 280;
const M = { top: 12, right: 16, bottom: 26, left: 52 };
const MONTH_START_DOY = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];

interface SeasonChartProps {
  daily: DailySeries;
  seriesKey: SeriesKey;
  date: string;
  compareYears: number[];
  onCompareYears: (years: number[]) => void;
  formatValue: (v: number) => string;
  unitLabel: string;
  minYear?: number;
}

export function SeasonChart({ daily, seriesKey, date, compareYears, onCompareYears, formatValue, unitLabel, minYear }: SeasonChartProps) {
  const { t, f } = useI18n();
  const year = yearOf(date);
  const firstYear = Math.max(yearOf(daily.start), minYear ?? 0);
  const lastYear = yearOf(daily.end);
  const years = useMemo(() => Array.from({ length: lastYear - firstYear + 1 }, (_, i) => lastYear - i), [firstYear, lastYear]);
  const [hoverDoy, setHoverDoy] = useState<number | null>(null);

  const clim = useMemo(() => climatology(daily, seriesKey, minYear), [daily, seriesKey, minYear]);
  const lines = useMemo(() => {
    const shown = [year, ...compareYears.filter((y) => y !== year)];
    return shown.map((y, i) => ({
      year: y,
      color: y === year ? SELECTED_LINE_COLOR : COMPARE_COLORS[(i - 1) % COMPARE_COLORS.length],
      values: movingAverage(yearSeries(daily, seriesKey, y), 7),
    }));
  }, [daily, seriesKey, year, compareYears]);
  const totals = useMemo(() => yearTotals(daily, seriesKey, minYear), [daily, seriesKey, minYear]);
  const strongest = totals.length ? totals.reduce((a, b) => (b.total > a.total ? b : a)) : null;
  const weakest = totals.length ? totals.reduce((a, b) => (b.total < a.total ? b : a)) : null;

  const yMax = Math.max(
    1e-6,
    ...(clim?.p75 ?? []),
    ...lines.flatMap((l) => l.values.map((v) => v ?? 0)),
  );
  const x = scaleLinear().domain([1, 365]).range([M.left, W - M.right]);
  const y = scaleLinear().domain([0, yMax * 1.05]).nice().range([H - M.bottom, M.top]);
  const path = d3line<number | null>()
    .defined((v) => v !== null)
    .x((_, i) => x(i + 1))
    .y((v) => y(v ?? 0));
  const band = clim
    ? d3area<number>()
        .x((_, i) => x(i + 1))
        .y0((_, i) => y(clim.p25[i]))
        .y1((v) => y(v))(clim.p75)
    : null;

  const dDoy = dayOfYear(date);
  const dValue = lines[0]?.values[dDoy - 1] ?? null;

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const doy = Math.round(x.invert(px));
    setHoverDoy(doy >= 1 && doy <= 365 ? doy : null);
  };

  const toggle = (y: number) =>
    onCompareYears(compareYears.includes(y) ? compareYears.filter((c) => c !== y) : [...compareYears, y].slice(-COMPARE_COLORS.length));

  const valueAt = (vals: Values, doy: number) => vals[doy - 1];

  return (
    <div className="season">
      <svg className="season__svg" viewBox={`0 0 ${W} ${H}`} role="img" onMouseMove={onMove} onMouseLeave={() => setHoverDoy(null)}
        aria-label={t("curve.aria", { unit: unitLabel, year: String(year), compare: compareYears.length ? t("curve.ariaCompare", { years: compareYears.join(", ") }) : "" })}>
        {y.ticks(5).map((tick) => (
          <g key={tick}>
            <line x1={M.left} x2={W - M.right} y1={y(tick)} y2={y(tick)} className="chart__grid" />
            <text x={M.left - 6} y={y(tick) + 4} textAnchor="end" className="chart__tick">{formatValue(tick)}</text>
          </g>
        ))}
        {MONTH_START_DOY.map((d, m) => (
          <g key={m}>
            <line x1={x(d)} x2={x(d)} y1={H - M.bottom} y2={H - M.bottom + 4} className="chart__axis" />
            <text x={x(d) + (x(MONTH_START_DOY[m + 1] ?? 366) - x(d)) / 2} y={H - 8} textAnchor="middle" className="chart__tick">{f.monthShort(m + 1)}</text>
          </g>
        ))}
        <line x1={M.left} x2={W - M.right} y1={H - M.bottom} y2={H - M.bottom} className="chart__axis" />
        {band && <path d={band} className="season__band" />}
        {clim && <path d={path(clim.median) ?? ""} className="season__median" />}
        {[...lines].reverse().map((l) => (
          <path key={l.year} d={path(l.values) ?? ""} fill="none" stroke={l.color} strokeWidth={l.year === year ? 2.6 : 1.5}
            strokeOpacity={l.year === year ? 1 : 0.85} />
        ))}
        {dValue !== null && (
          <g>
            <circle cx={x(dDoy)} cy={y(dValue)} r={6} fill={SELECTED_LINE_COLOR} stroke="#fff" strokeWidth={2} />
            <text x={x(dDoy)} y={y(dValue) - 10} textAnchor="middle" className="chart__tick chart__tick--strong">{f.dayMonth(date)}</text>
          </g>
        )}
        {hoverDoy !== null && <line x1={x(hoverDoy)} x2={x(hoverDoy)} y1={M.top} y2={H - M.bottom} className="chart__hover" />}
      </svg>
      <div className="season__readout" aria-live="polite">
        {hoverDoy !== null ? (
          <>
            <strong>{f.dayMonth(dateFromDayOfYear(2025, hoverDoy))}</strong>
            {lines.map((l) => {
              const v = valueAt(l.values, hoverDoy);
              return (
                <span key={l.year} style={{ color: l.color }}>
                  {l.year}: {v === null ? t("status.nodata") : formatValue(v)}
                </span>
              );
            })}
            {clim && <span className="muted">{t("curve.medianValue", { value: formatValue(clim.median[hoverDoy - 1]) })}</span>}
          </>
        ) : (
          <span className="muted">{t("curve.hint", { unit: unitLabel })}</span>
        )}
      </div>
      <div className="season__controls">
        <span className="legend__item"><span className="legend__line" style={{ background: SELECTED_LINE_COLOR }} />{t("curve.selected", { year: String(year) })}</span>
        {compareYears.filter((c) => c !== year).map((c, i) => (
          <button key={c} type="button" className="chip" onClick={() => toggle(c)} aria-label={t("curve.remove", { year: String(c) })}>
            <span className="legend__line" style={{ background: COMPARE_COLORS[i % COMPARE_COLORS.length] }} />
            {c} ✕
          </button>
        ))}
        <span className="legend__item"><span className="legend__band" />{t("curve.typical")}</span>
        <span className="legend__item"><span className="legend__line legend__line--dashed" />{t("curve.median")}</span>
        <label className="field field--inline">
          <span className="visually-hidden">{t("curve.addYearLabel")}</span>
          <select className="input input--small" value="" onChange={(e) => e.target.value && toggle(Number(e.target.value))}>
            <option value="">{t("curve.addYear")}</option>
            {years.filter((y) => y !== year && !compareYears.includes(y)).map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </label>
        {strongest && strongest.year !== year && !compareYears.includes(strongest.year) && (
          <button type="button" className="btn btn--small" onClick={() => toggle(strongest.year)}>{t("curve.strongest", { year: String(strongest.year) })}</button>
        )}
        {weakest && weakest.year !== year && !compareYears.includes(weakest.year) && (
          <button type="button" className="btn btn--small" onClick={() => toggle(weakest.year)}>{t("curve.weakest", { year: String(weakest.year) })}</button>
        )}
      </div>
    </div>
  );
}
