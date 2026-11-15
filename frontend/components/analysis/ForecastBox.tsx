/**
 * Outlook for the selected NUTS-2 region, above the short-term analysis: one main number (fire danger compared with
 * the usual for the season) and a three-part outlook for the next 10 days. Values come from /api/forecast/daily;
 * the summary is built in lib/forecast.ts. Shown only near the last data day.
 */
import { useI18n } from "../../i18n/I18n";
import { useApiQuery } from "../../hooks/useApiQuery";
import { RISK_COLOR } from "../../lib/colors";
import { outlookOf, type Change } from "../../lib/forecast";
import { fireApi } from "../../services/api/fireApi";
import type { RiskClass } from "../../services/api/types";
import { Tip } from "../ui/Elements";

const STALE_AFTER_DAYS = 2;
const LEVEL_KEY = {
  low: "fc.level.low", normal: "fc.level.normal", elevated: "fc.level.elevated", high: "fc.level.high",
  very_high: "fc.level.very_high",
} as const satisfies Record<RiskClass, string>;
const ARROW: Record<Change["kind"], string> = { lower: "↓", same: "→", higher: "↑", times: "↑" };

export function ForecastBox({ regionId, regionName }: { regionId: string; regionName: string }) {
  const { t, f } = useI18n();
  const daily = useApiQuery(`forecast|daily|${regionId}`, (signal) => fireApi.forecastDaily({ region_id: regionId }, signal));
  const status = useApiQuery("forecast|status", (signal) => fireApi.forecastStatus(signal));
  // Loading, errors and regions without a forecast stay quiet: the box is an extra, the page works without it.
  const outlook = daily.status === "success" ? outlookOf(daily.data.days) : null;
  if (!outlook || !daily.data) return null;

  const changeText = (c: Change) =>
    c.kind === "lower" ? t("fc.lower", { pct: c.percent })
      : c.kind === "higher" ? t("fc.higher", { pct: c.percent })
        : c.kind === "times" ? t("fc.times", { factor: f.one(c.factor) })
          : t("fc.same");
  const range = (a: string, b: string) => (a === b ? f.dayMonth(a) : `${f.dayMonth(a)} – ${f.dayMonth(b)}`);
  const st = status.data;
  const stale = st && (st.issue_date_age_days > STALE_AFTER_DAYS || st.warnings.length > 0);
  const main = outlook.change;
  const tone = main.kind === "lower" ? "low" : main.kind === "same" ? "normal" : main.kind === "higher" ? "elevated" : "high";

  return (
    <section className="ow-forecast" data-tone={tone} aria-label={t("fc.title", { region: regionName })} data-tour="forecast">
      <p className="ow-forecast__head">
        <span>{t("fc.title", { region: regionName })}</span>
        <Tip text={t("fc.help")} label={t("fc.about")} />
      </p>
      <p className="ow-forecast__main">
        <span className="ow-forecast__arrow" aria-hidden="true">{ARROW[main.kind]}</span>
        {changeText(main)}
      </p>
      <ul className="ow-forecast__parts">
        {outlook.parts.map((p) => (
          <li key={p.from} className="ow-forecast__part">
            <span className="ow-forecast__dot" style={{ background: RISK_COLOR[p.level] }} aria-hidden="true" />
            <span className="ow-forecast__when">{range(p.from, p.to)}</span>
            <span>{t(LEVEL_KEY[p.level])} {ARROW[p.change.kind]}</span>
          </li>
        ))}
      </ul>
      <p className="ow-forecast__foot">
        <span className={stale ? "ow-forecast__warn" : undefined}>{t("fc.issued", { date: f.dayMonth(daily.data.issue_date) })}</span>
        <span>{t(st?.weather_provider === "meteomatics" ? "fc.sourceMeteomatics" : "fc.source")}</span>
      </p>
    </section>
  );
}
