/** Top bar of page 1: reference day, confidence and method (spec §4, Seite 1). */
import { formatDate } from "../../lib/dates";
import {
  CONFIDENCE_HELP, CONFIDENCE_LABEL, METHOD_HELP, METHOD_LABEL, METHODS, type ConfidenceLevel, type Method,
} from "../../lib/methods";
import { InfoTip } from "../ui/InfoTip";
import { Segmented } from "../ui/Segmented";

interface SettingsBarProps {
  date: string;
  minDate: string;
  maxDate: string;
  onDate: (date: string) => void;
  conf: ConfidenceLevel;
  onConf: (c: ConfidenceLevel) => void;
  metric: Method;
  onMetric: (m: Method) => void;
  eventsAvailable: boolean;
}

export function SettingsBar(p: SettingsBarProps) {
  return (
    <div className="settings">
      <label className="field field--inline">
        <span className="field__label">Stichtag</span>
        <input type="date" className="input" value={p.date} min={p.minDate} max={p.maxDate}
          onChange={(e) => e.target.value && p.onDate(e.target.value)} />
        <button type="button" className="btn btn--small" onClick={() => p.onDate(p.maxDate)} disabled={p.date === p.maxDate}
          title={`Letzter Tag mit Daten: ${formatDate(p.maxDate)}`}>
          Heute
        </button>
      </label>
      <div className="settings__group">
        <Segmented label="Confidence" value={p.conf} onChange={p.onConf} size="small"
          options={(["nominal", "high"] as const).map((c) => ({ value: c, label: CONFIDENCE_LABEL[c], title: CONFIDENCE_HELP[c] }))} />
        <InfoTip text={`${CONFIDENCE_HELP.nominal} ${CONFIDENCE_HELP.high}`} label="Erklärung Confidence" />
      </div>
      <div className="settings__group">
        <Segmented label="Methode" value={p.metric} onChange={p.onMetric} size="small"
          options={METHODS.map((m) => ({
            value: m,
            label: METHOD_LABEL[m],
            title: METHOD_HELP[m],
            disabled: m === "events" && !p.eventsAvailable,
          }))} />
        <InfoTip text={METHODS.map((m) => `${METHOD_LABEL[m]}: ${METHOD_HELP[m]}`).join(" ")} label="Erklärung Methode" />
      </div>
    </div>
  );
}
