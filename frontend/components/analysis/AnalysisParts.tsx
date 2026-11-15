/** Building blocks of the analysis page: EFFIS-style header blocks, short-term cards, time slider, fire list. */
import { useMemo, useState, type ReactNode } from "react";
import type { DailySeries, SeasonPhase, SeriesKey, Values, WindowAnomaly } from "../../lib/analysis";
import { addDays, dateFromDayOfYear, dayOfYear, daysBetween, monthOf } from "../../lib/dates";
import type { FireUnit } from "../../lib/fireUnits";
import type { Method } from "../../lib/methods";
import type { EventSort } from "../../services/api/types";
import { useI18n } from "../../i18n/I18n";
import type { MessageKey } from "../../i18n/types";
import { unitAge } from "../../lib/mapFeatures";
import { ageColors } from "../../lib/palette";
import { usePrefs } from "../../hooks/usePrefs";
import { ytdStat, type YtdStat } from "../../lib/ytd";
import { Spinner, Tip } from "../ui/Elements";
import { Segmented } from "../ui/Segmented";
import { PLAYBACK_SPEEDS, type PlaybackSpeed } from "../../hooks/usePlayback";

/** Lower-case first letter, for method names used inside a sentence. */
export const inSentence = (s: string) => s.charAt(0).toLocaleLowerCase() + s.slice(1);

// ------------------------------------------------------------------ header blocks (year to date, side by side)

interface HeroSpec {
  id: string;
  key: SeriesKey;
  unit: string;
  sentence: MessageKey;
  /** counts (events, detections) are shown without decimals */
  integer?: boolean;
}

function HeroBlock({ spec, stat, loading }: { spec: HeroSpec; stat: YtdStat | null; loading: boolean }) {
  const { t, f } = useI18n();
  const num = (v: number) => (spec.integer && Math.abs(v) < 1e6 ? f.int(v) : f.compact(v));
  let compare: ReactNode = t(loading ? "hero.loading" : "hero.noCompare");
  if (stat && stat.value !== null && stat.lastYear) {
    const pct = stat.lastYear.value > 0 ? f.pctChange((stat.value - stat.lastYear.value) / stat.lastYear.value) : "–";
    const vars = { value: `${num(stat.lastYear.value)} ${spec.unit}`, date: f.dateLong(stat.lastYear.date), pct };
    compare = (
      <>
        {t(stat.value >= stat.lastYear.value ? "hero.above" : "hero.below", vars)}
        {stat.record && <> {stat.value > stat.record.value ? t("hero.newRecord") : t("hero.record", { value: num(stat.record.value), year: String(stat.record.year) })}</>}
      </>
    );
  }
  return (
    <article className="ow-hero__block">
      <p className="ow-hero__value">
        {stat?.value == null ? (loading ? <Spinner /> : t("ui.na")) : num(stat.value)} <span className="ow-hero__unit">{spec.unit}</span>
      </p>
      <p className="ow-hero__sentence">{t(spec.sentence)}</p>
      <p className="ow-hero__compare">{compare}</p>
    </article>
  );
}

/** Year to date for the selection: harmonised hotspots, FRP, and new events (raw detections without events). */
export function HeroBlocks({ daily, date, loading }: { daily: DailySeries | null; date: string; loading: boolean }) {
  const { t, f } = useI18n();
  const specs: HeroSpec[] = [
    { id: "fires", key: "fires", unit: t("unit.hotspots"), sentence: "hero.fires" },
    { id: "frp", key: "frp_sum", unit: "MW", sentence: "hero.frp" },
    daily?.events_new
      ? { id: "events", key: "events_new", unit: t("unit.events"), sentence: "hero.events", integer: true }
      : { id: "raw", key: "hotspots", unit: t("unit.detections"), sentence: "hero.raw", integer: true },
  ];
  const stats = useMemo(
    () => (daily ? { fires: ytdStat(daily, "fires", date), frp_sum: ytdStat(daily, "frp_sum", date), events_new: ytdStat(daily, "events_new", date), hotspots: ytdStat(daily, "hotspots", date) } : null),
    [daily, date],
  );
  return (
    <section className="ow-hero" aria-label={t("hero.aria")} data-tour="hero">
      <div className="ow-hero__grid">
        {specs.map((s) => (
          <HeroBlock key={s.id} spec={s} stat={stats ? stats[s.key as "fires" | "frp_sum" | "events_new" | "hotspots"] : null} loading={loading} />
        ))}
      </div>
      <p className="ow-hero__asof">{t("hero.asOf", { date: f.dateLong(date) })}</p>
    </section>
  );
}

// ------------------------------------------------------------------ short-term cards

function Card({ title, help, loading, children, action }: { title: string; help: string; loading?: boolean; children: ReactNode; action?: ReactNode }) {
  const { t } = useI18n();
  return (
    <article className="ow-card">
      <header className="ow-card__head">
        <h3 className="ow-card__title">{title}</h3>
        <Tip text={help} label={t("card.about", { title })} />
        {loading && <Spinner />}
      </header>
      <div className="ow-card__body">{children}</div>
      {action}
    </article>
  );
}

export function WeekCard({ anomaly, method, unit, loading }: { anomaly: WindowAnomaly | null; method: Method; unit: string; loading: boolean }) {
  const { t, f } = useI18n();
  let main = t("ui.na");
  let sub: ReactNode = t(loading ? "week.computing" : "week.noData");
  if (anomaly && anomaly.value !== null) {
    const typical = anomaly.median ?? 0;
    let text: string;
    if (anomaly.factor !== null) {
      main = t("week.factor", { factor: f.factor(anomaly.factor) });
      text = t(anomaly.factor >= 1.2 ? "week.more" : anomaly.factor <= 0.8 ? "week.less" : "week.same");
    } else {
      main = f.signed(anomaly.value - typical);
      text = t(typical === 0 ? "week.noneUsual" : "week.diff");
    }
    sub = (
      <>
        {text}
        <span className="ow-card__meta">
          {t("week.meta", { value: f.method(method, anomaly.value), unit, rank: anomaly.rank ?? 0, of: anomaly.rank_of, usual: f.method(method, typical) })}
        </span>
      </>
    );
  }
  const level = anomaly?.factor != null && anomaly.factor >= 1.5 ? "high" : anomaly?.factor != null && anomaly.factor <= 0.67 ? "low" : "normal";
  return (
    <Card title={t("week.title")} loading={loading} help={t("week.help", { method: inSentence(t(`method.${method}.long`)) })}>
      <p className={`ow-card__value ow-card__value--${level}`}>{main}</p>
      <p className="ow-card__sub">{sub}</p>
    </Card>
  );
}

export function ActiveCard({ active, previous, fresh, kind, loading }: {
  active: number | null; previous: number | null; fresh: number | null; kind: "event" | "cell"; loading: boolean;
}) {
  const { t, f } = useI18n();
  const delta = active !== null && previous !== null ? active - previous : null;
  return (
    <Card title={t(kind === "event" ? "active.events" : "active.cells")} loading={loading}
      help={t(kind === "event" ? "active.helpEvents" : "active.helpCells")}>
      <p className="ow-card__value">{active === null ? t("ui.na") : f.int(active)}</p>
      <p className="ow-card__sub">
        {delta === null ? "" : delta === 0 ? t("active.same") : t(delta > 0 ? "active.more" : "active.fewer", { count: Math.abs(delta) })}
        {fresh !== null && <span className="ow-card__meta">{t("active.new", { count: fresh })}</span>}
      </p>
    </Card>
  );
}

export function SeasonCard({ phase, date, loading, curve }: { phase: SeasonPhase | null; date: string; loading: boolean; curve: number[] | null }) {
  const { t, f } = useI18n();
  const year = Number(date.slice(0, 4));
  const peakDate = phase && phase.peakDoy ? dateFromDayOfYear(year, phase.peakDoy) : null;
  let sub = "";
  if (phase && phase.phase !== "no_season") {
    sub = phase.daysToPeak > 0
      ? t("season.toPeak", { count: phase.daysToPeak })
      : phase.daysToPeak < 0 ? t("season.sincePeak", { count: -phase.daysToPeak }) : t("season.peakToday");
  }
  const max = curve ? Math.max(...curve, 1e-9) : 1;
  const doy = dayOfYear(date) - 1;
  return (
    <Card title={t("season.title")} loading={loading} help={t("season.help")}>
      <p className="ow-card__value ow-card__value--text">{phase ? t(`phase.${phase.phase}`) : t("ui.na")}</p>
      <p className="ow-card__sub">
        {sub}
        {peakDate && <span className="ow-card__meta">{t("season.typical", { date: f.dayMonth(peakDate) })}</span>}
        {phase?.secondaryPeakDoy && (
          <span className="ow-card__meta">{t("season.second", { month: f.monthLong(monthOf(dateFromDayOfYear(year, phase.secondaryPeakDoy))) })}</span>
        )}
      </p>
      {curve && (
        <svg className="ow-card__spark" viewBox="0 0 365 40" preserveAspectRatio="none" role="img" aria-label={t("season.aria")}>
          <path d={`M0,40 ${curve.map((v, i) => `L${i},${40 - (36 * v) / max}`).join(" ")} L364,40 Z`} className="ow-spark__area" />
          <line x1={doy} x2={doy} y1={0} y2={40} className="ow-spark__marker" />
        </svg>
      )}
    </Card>
  );
}

export function StrongestCard({ unit, name, loading, onShow }: { unit: FireUnit | null; name: string; loading: boolean; onShow: () => void }) {
  const { t, f } = useI18n();
  return (
    <Card title={t("strong.title")} loading={loading} help={t("strong.help")}
      action={unit ? <button type="button" className="ow-card__action" onClick={onShow}>{t("strong.show")}</button> : undefined}>
      {unit ? (
        <>
          <p className="ow-card__value ow-card__value--text">{name}</p>
          <p className="ow-card__sub">
            {t("strong.frp", { value: f.compact(unit.frp_sum) })}
            <span className="ow-card__meta">
              {t("strong.since", { date: f.date(unit.first_seen) })}
              {unit.area_km2 !== null && `, ${t("strong.area", { area: f.km2(unit.area_km2) })}`}
            </span>
          </p>
        </>
      ) : (
        <p className="ow-card__sub">{t(loading ? "ui.loading" : "strong.none")}</p>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ time slider

export function TimeSlider({ value, anchor, min, max, onChange, bars, barsLabel, playback }: {
  value: string; anchor: string; min: string; max: string; onChange: (d: string) => void; bars: Values | null; barsLabel: string;
  playback: { playing: boolean; onToggle: () => void; speed: PlaybackSpeed; onSpeed: (s: PlaybackSpeed) => void };
}) {
  const { t, f } = useI18n();
  const total = daysBetween(min, max);
  const pos = daysBetween(min, value);
  const anchorPos = daysBetween(min, anchor);
  const barMax = useMemo(() => Math.max(1e-9, ...(bars ?? []).map((v) => v ?? 0)), [bars]);
  const diff = daysBetween(anchor, value);
  const pct = (i: number) => (total === 0 ? 0 : (i / total) * 100);
  return (
    <div className="ow-slider" data-tour="slider">
      <div className="ow-slider__head">
        <button type="button" className="ow-btn ow-btn--small ow-btn--icon ow-slider__play" onClick={playback.onToggle} disabled={total === 0}
          aria-pressed={playback.playing} aria-label={t(playback.playing ? "slider.pause" : "slider.play")} title={t(playback.playing ? "slider.pause" : "slider.play")}>
          {playback.playing
            ? <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 3h2.5v10H4.5zM9 3h2.5v10H9z" fill="currentColor" /></svg>
            : <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 2.5v11l9-5.5z" fill="currentColor" /></svg>}
        </button>
        <Segmented label={t("slider.speed")} hideLabel size="small" value={playback.speed} onChange={playback.onSpeed}
          options={PLAYBACK_SPEEDS.map((s) => ({ value: s, label: `${f.factor(s)}×` }))} />
        <button type="button" className="ow-btn ow-btn--small ow-btn--icon" onClick={() => onChange(addDays(value, -1))} disabled={value <= min} aria-label={t("slider.back")}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
        </button>
        {/* While playing, a screen reader would announce every day: the date is only announced on manual steps. */}
        <output className="ow-slider__value" aria-live={playback.playing ? "off" : "polite"}>
          {f.date(value)}
          <span className="ow-muted">{diff === 0 ? t("slider.atReference") : t("slider.offset", { sign: diff > 0 ? "+" : "−", count: Math.abs(diff) })}</span>
        </output>
        <button type="button" className="ow-btn ow-btn--small ow-btn--icon" onClick={() => onChange(addDays(value, 1))} disabled={value >= max} aria-label={t("slider.forward")}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 3 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
        </button>
        {diff !== 0 && <button type="button" className="ow-btn ow-btn--small ow-btn--ghost" onClick={() => onChange(anchor)}>{t("slider.reset")}</button>}
      </div>
      {bars && (
        <svg className="ow-slider__bars" viewBox={`0 0 ${Math.max(1, total + 1)} 30`} preserveAspectRatio="none" role="img" aria-label={t("slider.bars", { metric: inSentence(barsLabel) })}>
          {bars.map((v, i) => (
            <rect key={i} x={i} width={0.86} className={i === pos ? "ow-slider__bar ow-slider__bar--on" : v === null ? "ow-slider__bar ow-slider__bar--none" : "ow-slider__bar"}
              y={v === null ? 27 : 30 - (28 * v) / barMax} height={v === null ? 3 : (28 * v) / barMax} />
          ))}
        </svg>
      )}
      <div className="ow-slider__track">
        <span className="ow-slider__anchor" style={{ insetInlineStart: `${pct(anchorPos)}%` }} aria-hidden="true" />
        <input type="range" min={0} max={total} step={1} value={pos} className="ow-slider__input" aria-label={t("slider.aria")} aria-valuetext={f.date(value)}
          onChange={(e) => onChange(addDays(min, Number(e.target.value)))} />
      </div>
      <div className="ow-slider__scale" aria-hidden="true">
        <span>{f.dayMonth(min)}</span>
        <span>{t("slider.reference", { date: f.dayMonth(anchor) })}</span>
        <span>{f.dayMonth(max)}</span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ list of fires next to the map

const PAGE = 40;

export function FireList({ units, kind, sort, onSort, selectedId, onSelect, nameOf, total, truncated }: {
  units: FireUnit[]; kind: "event" | "cell"; sort: EventSort; onSort: (s: EventSort) => void; selectedId: string | null;
  onSelect: (u: FireUnit) => void; nameOf: (u: FireUnit) => string; total: number; truncated: boolean;
}) {
  const { prefs } = usePrefs();
  const { t, f } = useI18n();
  const colors = ageColors(prefs.palette);
  const [shown, setShown] = useState(PAGE);
  const sorts: EventSort[] = kind === "event" ? ["frp_sum", "area_km2", "duration_days", "hotspots", "start", "last_seen"] : ["frp_sum", "duration_days", "hotspots", "last_seen"];
  const status = (u: FireUnit) => {
    if (u.days_since_last === 0) return u.isNew ? t("unitStatus.newToday") : t("unitStatus.activeFor", { count: u.duration_days });
    return t(u.days_since_last > 2 ? "unitStatus.ended" : "unitStatus.lastSeen", { count: u.days_since_last });
  };
  return (
    <div className="ow-list">
      <div className="ow-list__head">
        <span className="ow-small ow-muted">
          {t(kind === "event" ? "list.countEvents" : "list.countCells", { count: total })}{truncated ? `, ${t("list.strongest")}` : ""}
        </span>
        <label className="ow-list__sort">
          <span className="ow-small ow-muted">{t("list.sortBy")}</span>
          <select className="ow-input ow-input--small" value={sort} onChange={(e) => onSort(e.target.value as EventSort)}>
            {sorts.map((s) => <option key={s} value={s}>{t(`sort.${s}`)}</option>)}
          </select>
        </label>
      </div>
      <ul className="ow-list__items">
        {units.slice(0, shown).map((u) => {
          const age = unitAge(u);
          return (
            <li key={u.id}>
              <button type="button" className="ow-unit" aria-pressed={selectedId === u.id} onClick={() => onSelect(u)}>
                <span className="ow-unit__swatch" style={{ background: colors[age] }} title={t(`age.${age}`)} />
                <span className="ow-unit__main">
                  <span className="ow-unit__name">{nameOf(u)}</span>
                  <span className="ow-unit__status">{status(u)}</span>
                  <span className="ow-unit__facts">
                    <span>{f.compact(u.frp_sum)} MW</span>
                    {u.area_km2 !== null && <span>{f.km2(u.area_km2)}</span>}
                    <span>{t("unit.hotspotsCount", { count: u.hotspots })}</span>
                    {u.trend && <span>{t(`trend.${u.trend}`)}</span>}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {units.length > shown && (
        <button type="button" className="ow-btn ow-btn--small" onClick={() => setShown((n) => n + PAGE)}>{t("list.more", { count: Math.min(PAGE, units.length - shown) })}</button>
      )}
    </div>
  );
}
