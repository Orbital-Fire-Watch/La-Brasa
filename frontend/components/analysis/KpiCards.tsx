/** "Kurzzeitanalyse": the four cards at the top of page 2 (spec §7.3). */
import type { ReactNode } from "react";
import type { SeasonPhase, WindowAnomaly } from "../../lib/analysis";
import { dateFromDayOfYear, dayOfYear, formatDate, monthLong, monthOf } from "../../lib/dates";
import type { FireUnit } from "../../lib/fireUnits";
import { formatCompact, formatInt, formatKm2, formatSigned, plural } from "../../lib/format";
import { METHOD_LONG, type Method } from "../../lib/methods";
import { formatMethodValue, METHOD_UNIT } from "../../lib/units";
import { InfoTip } from "../ui/InfoTip";
import { Spinner } from "../ui/Status";

function Card({ title, help, loading, children, onClick, actionLabel }: {
  title: string; help: string; loading?: boolean; children: ReactNode; onClick?: () => void; actionLabel?: string;
}) {
  return (
    <article className="kpi">
      <header className="kpi__head">
        <h3 className="kpi__title">{title}</h3>
        <InfoTip text={help} label={`Erklärung: ${title}`} />
        {loading && <Spinner />}
      </header>
      <div className="kpi__body">{children}</div>
      {onClick && (
        <button type="button" className="kpi__action" onClick={onClick}>
          {actionLabel}
        </button>
      )}
    </article>
  );
}

export function WeekCard({ anomaly, method, loading }: { anomaly: WindowAnomaly | null; method: Method; loading: boolean }) {
  const unit = METHOD_UNIT[method];
  let main: ReactNode = "–";
  let sub: ReactNode = loading ? "Wird berechnet …" : "Keine vollständigen Daten für diese Woche.";
  if (anomaly && anomaly.value !== null) {
    const typical = anomaly.median ?? 0;
    if (anomaly.factor !== null) {
      main = `${anomaly.factor.toLocaleString("de-DE")}×`;
      sub = anomaly.factor >= 1.2 ? "so viel wie üblich" : anomaly.factor <= 0.8 ? "des üblichen Werts" : "etwa wie üblich";
    } else {
      main = formatSigned(anomaly.value - typical);
      sub = typical === 0 ? "sonst keine Feuer in dieser Woche" : "Abweichung";
    }
    sub = (
      <>
        {sub}
        <br />
        <span className="muted">
          {formatMethodValue(method, anomaly.value)} {unit} · Platz {anomaly.rank} von {anomaly.rank_of} · üblich: {formatMethodValue(method, typical)}
        </span>
      </>
    );
  }
  const level = anomaly?.factor != null && anomaly.factor >= 1.5 ? "high" : anomaly?.factor != null && anomaly.factor <= 0.67 ? "low" : "normal";
  return (
    <Card title="Diese Woche im Vergleich" loading={loading}
      help={`Summe ${METHOD_LONG[method]} der letzten 7 Tage bis zum Stichtag, verglichen mit denselben 7 Tagen in allen anderen Jahren (Median). Platz 1 = höchster Wert.`}>
      <p className={`kpi__value kpi__value--${level}`}>{main}</p>
      <p className="kpi__sub">{sub}</p>
    </Card>
  );
}

export function ActiveCard({ active, previous, fresh, kind, loading }: {
  active: number | null; previous: number | null; fresh: number | null; kind: "event" | "cell"; loading: boolean;
}) {
  const delta = active !== null && previous !== null ? active - previous : null;
  return (
    <Card title={kind === "event" ? "Aktive Ereignisse" : "Aktive Gebiete"} loading={loading}
      help={kind === "event"
        ? "Ereignisse mit mindestens einem Hotspot am Stichtag, verglichen mit dem Vortag. Neu = Beginn am Stichtag."
        : "Ersatz ohne Ereignisse: H3-Zellen (ca. 36 km²) mit Hotspot am Stichtag, verglichen mit dem Vortag."}>
      <p className="kpi__value">{active === null ? "–" : formatInt(active)}</p>
      <p className="kpi__sub">
        {delta === null ? "" : delta === 0 ? "gleich viele wie am Vortag" : `${delta > 0 ? "▲" : "▼"} ${formatInt(Math.abs(delta))} ${delta > 0 ? "mehr" : "weniger"} als am Vortag`}
        {fresh !== null && (
          <>
            <br />
            <span className="muted">{plural(fresh, "neu", "neu")} seit gestern</span>
          </>
        )}
      </p>
    </Card>
  );
}

const PHASE_TEXT: Record<SeasonPhase["phase"], string> = {
  pre_season: "vor der Saison",
  rising: "Anstieg",
  peak: "Hochphase",
  declining: "Abklingen",
  post_season: "nach der Saison",
  no_season: "keine Saison erkennbar",
};

export function SeasonCard({ phase, date, loading, curve }: { phase: SeasonPhase | null; date: string; loading: boolean; curve: number[] | null }) {
  const year = Number(date.slice(0, 4));
  const peakDate = phase && phase.peakDoy ? dateFromDayOfYear(year, phase.peakDoy) : null;
  let sub = "";
  if (phase && phase.phase !== "no_season") {
    sub = phase.daysToPeak > 0 ? `noch ${phase.daysToPeak} Tage bis zum Peak` : phase.daysToPeak < 0 ? `Peak vor ${-phase.daysToPeak} Tagen` : "Peak heute";
  }
  const max = curve ? Math.max(...curve, 1e-9) : 1;
  const doy = dayOfYear(date) - 1;
  return (
    <Card title="Saisonphase" loading={loading}
      help="Typische Saison aus allen Jahren: Median je Kalendertag, über 15 Tage geglättet. Beginn/Ende bei 10 % bzw. 90 % der Jahressumme, Hochphase ±7 Tage um den Peak.">
      <p className="kpi__value kpi__value--text">{phase ? PHASE_TEXT[phase.phase] : "–"}</p>
      <p className="kpi__sub">
        {sub}
        {peakDate && <span className="muted"><br />typischer Peak: {formatDate(peakDate).replace(/ \d{4}$/, "")}</span>}
        {phase?.secondaryPeakDoy && (
          <span className="muted"><br />Nebensaison im {monthLong(monthOf(dateFromDayOfYear(year, phase.secondaryPeakDoy)))}</span>
        )}
      </p>
      {curve && (
        <svg className="kpi__spark" viewBox="0 0 365 40" preserveAspectRatio="none" role="img" aria-label="Typischer Saisonverlauf mit Stichtag">
          <path d={`M0,40 ${curve.map((v, i) => `L${i},${40 - (36 * v) / max}`).join(" ")} L364,40 Z`} fill="#fde0c5" stroke="#e8590c" strokeWidth="1" />
          <line x1={doy} x2={doy} y1={0} y2={40} stroke="#1c1917" strokeWidth="2" />
        </svg>
      )}
    </Card>
  );
}

export function StrongestCard({ unit, name, loading, onShow }: { unit: FireUnit | null; name: string; loading: boolean; onShow: () => void }) {
  return (
    <Card title="Stärkstes Feuer" loading={loading} onClick={unit ? onShow : undefined} actionLabel="Auf der Karte zeigen →"
      help="Ereignis (bzw. ohne Ereignisse: H3-Zelle) mit der größten harmonisierten FRP-Summe im Rückblick-Fenster.">
      {unit ? (
        <>
          <p className="kpi__value kpi__value--text">{name}</p>
          <p className="kpi__sub">
            {formatCompact(unit.frp_sum)} MW FRP-Summe
            <br />
            <span className="muted">
              seit {formatDate(unit.first_seen)}
              {unit.area_km2 !== null && ` · ca. ${formatKm2(unit.area_km2)}`}
            </span>
          </p>
        </>
      ) : (
        <p className="kpi__sub">{loading ? "Wird geladen …" : "Keine Feuer im Zeitraum."}</p>
      )}
    </Card>
  );
}
