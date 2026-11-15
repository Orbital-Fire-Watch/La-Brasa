/**
 * Warning box above the short-term analysis: probability of a big fire day (≥ 100 MW in the region) for the next
 * 10 days, per NUTS-2 region. Shown only near the last data day (lib/forecast.ts); values come unchanged from
 * /api/forecast/daily.
 */
import { useMemo } from "react";
import { useApiQuery } from "../../hooks/useApiQuery";
import { useI18n } from "../../i18n/I18n";
import { LOCALES } from "../../i18n/locales";
import { RISK_COLOR, RISK_TEXT } from "../../lib/colors";
import { FORECAST_PALE_FROM_LEAD, firstElevated, RISK_ORDER, worstClass, type ForecastScope } from "../../lib/forecast";
import { fireApi } from "../../services/api/fireApi";
import type { ForecastDay, RiskClass } from "../../services/api/types";
import { ErrorNote, Loading, Tip } from "../ui/Elements";

const STALE_AFTER_DAYS = 2;
const CLASS_KEY = {
  low: "fc.class.low", normal: "fc.class.normal", elevated: "fc.class.elevated", high: "fc.class.high", very_high: "fc.class.very_high",
} as const satisfies Record<RiskClass, string>;

export function ForecastBox({ scope, regionName }: { scope: ForecastScope; regionName: (id: string) => string }) {
  const { t, f, locale } = useI18n();
  const daily = useApiQuery("forecast|daily", (signal) => fireApi.forecastDaily({}, signal));
  const status = useApiQuery("forecast|status", (signal) => fireApi.forecastStatus(signal));
  const pct = useMemo(() => {
    const fine = new Intl.NumberFormat(LOCALES[locale].intl, { style: "percent", maximumFractionDigits: 1 });
    const whole = new Intl.NumberFormat(LOCALES[locale].intl, { style: "percent", maximumFractionDigits: 0 });
    return (p: number) => (p < 0.001 ? `< ${fine.format(0.001)}` : p < 0.1 ? fine.format(p) : whole.format(p));
  }, [locale]);

  const byRegion = useMemo(() => {
    const m = new Map<string, ForecastDay[]>();
    for (const d of daily.data?.days ?? []) m.set(d.region_id, [...(m.get(d.region_id) ?? []), d]);
    return m;
  }, [daily.data]);
  const rows = scope.ids
    .map((id) => ({ id, days: byRegion.get(id) ?? [] }))
    .filter((r) => r.days.length > 0)
    .sort((a, b) => RISK_ORDER.indexOf(worstClass(b.days)) - RISK_ORDER.indexOf(worstClass(a.days)));

  if (daily.status === "loading") return <section className="ow-forecast"><Loading label={t("fc.loading")} height={80} /></section>;
  if (daily.status === "error") return <section className="ow-forecast"><ErrorNote error={daily.error} onRetry={daily.reload} /></section>;
  if (!daily.data) return null;

  const all = rows.flatMap((r) => r.days);
  const worst = all.length ? worstClass(all) : "low";
  const first = firstElevated([...all].sort((a, b) => a.target_date.localeCompare(b.target_date)));
  const st = status.data;
  const issue = f.date(daily.data.issue_date);
  const headline = first ? t("fc.headlineRisk", { date: f.dayMonth(first.target_date) }) : t("fc.headlineCalm");

  return (
    <section className="ow-forecast" data-level={worst} aria-label={t("fc.title")} style={{ borderLeftColor: RISK_COLOR[worst] }}>
      <header className="ow-forecast__head">
        <strong>{t("fc.title")}</strong>
        <span className="ow-forecast__headline">{headline}</span>
        <Tip text={t("fc.help")} label={t("fc.about")} />
      </header>
      {scope.kind === "province" && <p className="ow-forecast__note">{t("fc.noteProvince")}</p>}
      {scope.kind === "area" && <p className="ow-forecast__note">{t("fc.noteArea")}</p>}
      {rows.length === 0 && <p className="ow-forecast__note">{t("fc.none")}</p>}
      <div className="ow-forecast__rows">
        {rows.map((r) => (
          <div key={r.id} className="ow-forecast__row">
            {rows.length > 1 || scope.kind !== "region" ? <span className="ow-forecast__region">{regionName(r.id)}</span> : null}
            <ol className="ow-forecast__days">
              {r.days.map((d) => (
                <li key={d.target_date} className="ow-forecast__day"
                  style={{ background: RISK_COLOR[d.risk_class], color: RISK_TEXT[d.risk_class],
                    opacity: d.lead_days >= FORECAST_PALE_FROM_LEAD ? 0.6 : 1 }}
                  title={t("fc.tooltip", {
                    p: pct(d.p_big_fire_day), lo: pct(d.p_big_fire_day_lo), hi: pct(d.p_big_fire_day_hi),
                    clim: pct(d.p_clim_big_fire_day), issue, lead: d.lead_days, cls: t(CLASS_KEY[d.risk_class]),
                  }) + (d.source === "climatology" ? ` ${t("fc.climOnly")}` : "")
                    + (d.model_version.includes("noweather") ? ` ${t("fc.noWeather")}` : "")}>
                  <span className="ow-forecast__date">{f.dayMonth(d.target_date)}</span>
                  <span className="ow-forecast__pct">{pct(d.p_big_fire_day)}</span>
                  <span className="ow-forecast__cls">{t(CLASS_KEY[d.risk_class])}</span>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
      <footer className="ow-forecast__foot">
        <span>{t("fc.issued", { date: issue })}</span>
        {st && (st.issue_date_age_days > STALE_AFTER_DAYS || st.warnings.length > 0) && (
          <span className="ow-forecast__warn">{t("fc.stale", { date: f.date(st.issue_date) })}</span>
        )}
        {st && !st.weather_used && <span className="ow-forecast__warn">{t("fc.noWeather")}</span>}
        <span>{t(st?.weather_provider === "meteomatics" ? "fc.sourceMeteomatics" : "fc.source")}</span>
      </footer>
    </section>
  );
}
