/** List right of the map: events (or H3 cells as fallback), sortable, with key facts per entry (spec §6.9, §7.6). */
import { useState } from "react";
import { AGE_COLOR, AGE_LABEL } from "../../lib/colors";
import { formatDate } from "../../lib/dates";
import type { FireUnit } from "../../lib/fireUnits";
import { formatCompact, formatInt, formatKm2, formatOne } from "../../lib/format";
import { unitAge } from "../../lib/mapFeatures";
import type { EventSort } from "../../services/api/types";

export const SORT_LABEL: Record<EventSort, string> = {
  frp_sum: "Stärke (FRP)",
  area_km2: "Fläche",
  duration_days: "Dauer",
  hotspots: "Hotspots",
  start: "Beginn",
  last_seen: "Zuletzt gesehen",
};

const TREND: Record<NonNullable<FireUnit["trend"]>, { icon: string; label: string }> = {
  growing: { icon: "↗", label: "wächst" },
  stable: { icon: "→", label: "stabil" },
  shrinking: { icon: "↘", label: "nimmt ab" },
};

const PAGE = 60;

interface UnitListProps {
  units: FireUnit[];
  kind: "event" | "cell";
  sort: EventSort;
  onSort: (s: EventSort) => void;
  selectedId: string | null;
  onSelect: (u: FireUnit) => void;
  nameOf: (u: FireUnit) => string;
  total: number;
  truncated: boolean;
}

function statusText(u: FireUnit): string {
  if (u.days_since_last === 0) return u.isNew ? "neu, heute aktiv" : `aktiv seit ${u.duration_days} ${u.duration_days === 1 ? "Tag" : "Tagen"}`;
  if (u.days_since_last > 2) return `erloschen, zuletzt vor ${u.days_since_last} Tagen`;
  return `zuletzt vor ${u.days_since_last} ${u.days_since_last === 1 ? "Tag" : "Tagen"}`;
}

export function UnitList({ units, kind, sort, onSort, selectedId, onSelect, nameOf, total, truncated }: UnitListProps) {
  const [shown, setShown] = useState(PAGE);
  const sorts: EventSort[] = kind === "event" ? ["frp_sum", "area_km2", "duration_days", "hotspots", "start", "last_seen"] : ["frp_sum", "duration_days", "hotspots", "last_seen"];
  return (
    <div className="units">
      <div className="units__head">
        <label className="field field--inline">
          <span className="field__label">Sortieren nach</span>
          <select className="input" value={sort} onChange={(e) => onSort(e.target.value as EventSort)}>
            {sorts.map((s) => (
              <option key={s} value={s}>{SORT_LABEL[s]}</option>
            ))}
          </select>
        </label>
        <span className="muted small">
          {formatInt(total)} {kind === "event" ? (total === 1 ? "Ereignis" : "Ereignisse") : total === 1 ? "Gebiet" : "Gebiete"}
          {truncated && ` (die ${units.length} stärksten)`}
        </span>
      </div>
      <ol className="units__list">
        {units.slice(0, shown).map((u) => {
          const age = unitAge(u);
          return (
            <li key={u.id}>
              <button type="button" className="unit" aria-pressed={u.id === selectedId} onClick={() => onSelect(u)}>
                <span className="unit__swatch" style={{ background: AGE_COLOR[age] }} aria-hidden="true" />
                <span className="unit__main">
                  <span className="unit__name">{nameOf(u)}</span>
                  <span className="unit__status">
                    {AGE_LABEL[age]} · {statusText(u)}
                    {u.trend && <span title={`Trend: ${TREND[u.trend].label}`}> · {TREND[u.trend].icon} {TREND[u.trend].label}</span>}
                  </span>
                  <span className="unit__facts">
                    <span><b>{formatCompact(u.frp_sum)}</b> MW</span>
                    <span><b>{formatInt(u.hotspots)}</b> Hotspots</span>
                    {u.area_km2 !== null ? <span><b>{formatKm2(u.area_km2)}</b></span> : <span><b>{formatOne(u.fires)}</b> harm.</span>}
                    <span>{formatDate(u.first_seen).replace(/ \d{4}$/, "")}–{formatDate(u.last_seen).replace(/ \d{4}$/, "")}</span>
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {units.length > shown && (
        <button type="button" className="btn btn--small units__more" onClick={() => setShown((n) => n + PAGE)}>
          Weitere {Math.min(PAGE, units.length - shown)} anzeigen
        </button>
      )}
    </div>
  );
}
