/** Tiles of the start page sidebar and the floating map elements (drawing bar, info boxes). */
import { cellToLatLng } from "h3-js";
import { useMemo, useState } from "react";
import { Segmented } from "../ui/Segmented";
import { useApiQuery } from "../../hooks/useApiQuery";
import { useAppData } from "../../hooks/useAppData";
import type { DrawMode } from "../../hooks/useDrawTool";
import { METHODS, type ConfidenceLevel, type Method } from "../../lib/methods";
import { regionAt } from "../../lib/regions";
import { fireApi } from "../../services/api/fireApi";
import { isGridCount, type RegionFeature, type RegionsResponse } from "../../services/api/types";
import { useI18n } from "../../i18n/I18n";
import { useRegionName } from "../../hooks/useSelectionInfo";
import { ErrorNote, Flag, Loading, Tile, Tip } from "../ui/Elements";

// ------------------------------------------------------------------ settings (first tile)

export function SettingsTile(p: {
  date: string; minDate: string; maxDate: string; onDate: (d: string) => void;
  conf: ConfidenceLevel; onConf: (c: ConfidenceLevel) => void;
  method: Method; onMethod: (m: Method) => void; eventsAvailable: boolean;
}) {
  const { t, f } = useI18n();
  return (
    <Tile title={t("settings.title")} tour="settings">
      <div className="ow-form">
        <div className="ow-field">
          <label className="ow-field__label" htmlFor="ow-date">{t("settings.date")}</label>
          <div className="ow-field__row">
            <input id="ow-date" type="date" className="ow-input" value={p.date} min={p.minDate} max={p.maxDate}
              onChange={(e) => e.target.value && p.onDate(e.target.value)} />
            <button type="button" className="ow-btn ow-btn--small" onClick={() => p.onDate(p.maxDate)} disabled={p.date === p.maxDate}
              title={t("settings.latestTitle", { date: f.date(p.maxDate) })}>{t("settings.latest")}</button>
          </div>
        </div>
        <div className="ow-field ow-field--seg">
          <Segmented label={t("conf.label")} value={p.conf} onChange={p.onConf} size="small"
            options={(["nominal", "high"] as const).map((c) => ({ value: c, label: t(`conf.${c}`) }))} />
          <Tip text={t("conf.help")} label={t("settings.aboutConf")} />
        </div>
        <div className="ow-field ow-field--seg">
          <Segmented label={t("settings.method")} value={p.method} onChange={p.onMethod} size="small"
            options={METHODS.map((m) => ({ value: m, label: t(`method.${m}`), disabled: m === "events" && !p.eventsAvailable }))} />
          <Tip text={METHODS.map((m) => `${t(`method.${m}`)}: ${t(`method.${m}.help`)}`).join("\n\n")} label={t("settings.aboutMethods")} />
        </div>
      </div>
    </Tile>
  );
}

// ------------------------------------------------------------------ predefined areas with flags and the path back up

interface Node {
  feature: RegionFeature;
  children: Node[];
}

const collator = new Intl.Collator("es");
const COUNTRY_ORDER = ["ES", "PT"];

function buildTree(regions: RegionsResponse): Node[] {
  const byParent = new Map<string | null, RegionFeature[]>();
  for (const r of regions.features) {
    const list = byParent.get(r.properties.parent) ?? [];
    list.push(r);
    byParent.set(r.properties.parent, list);
  }
  const build = (r: RegionFeature): Node => ({
    feature: r,
    children: (byParent.get(r.properties.id) ?? []).sort((a, b) => collator.compare(a.properties.name, b.properties.name)).map(build),
  });
  return (byParent.get(null) ?? [])
    .filter((r) => r.properties.level === "country")
    .sort((a, b) => COUNTRY_ORDER.indexOf(a.properties.id) - COUNTRY_ORDER.indexOf(b.properties.id))
    .map(build);
}

/**
 * "Spain and Portugal › Spain › Galicia": every step is a button, so one click goes back to the whole country.
 * The × clears the selection.
 */
export function AreaPath({ path, onSelect }: { path: RegionFeature[]; onSelect: (id: string | null) => void }) {
  const { t } = useI18n();
  const name = useRegionName();
  if (path.length === 0) return null;
  return (
    <nav className="ow-path" aria-label={t("area.path")}>
      <ol>
        <li><button type="button" onClick={() => onSelect(null)}>{t("area.allName")}</button></li>
        {path.map((r, i) => (
          <li key={r.properties.id}>
            {i === path.length - 1
              ? <span aria-current="location">{name(r)}</span>
              : <button type="button" onClick={() => onSelect(r.properties.id)}>{name(r)}</button>}
          </li>
        ))}
      </ol>
      <button type="button" className="ow-path__clear" onClick={() => onSelect(null)} aria-label={t("area.clear")} title={t("area.clear")}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" /></svg>
      </button>
    </nav>
  );
}

export function RegionTile({ regions, selectedId, path, onSelect }: {
  regions: RegionsResponse | null; selectedId: string | null; path: RegionFeature[]; onSelect: (id: string | null) => void;
}) {
  const { t } = useI18n();
  const name = useRegionName();
  const [query, setQuery] = useState("");
  const [toggled, setToggled] = useState<Map<string, boolean>>(new Map());
  const forced = useMemo(() => new Set(path.slice(0, -1).map((r) => r.properties.id)), [path]);
  const isOpen = (id: string) => toggled.get(id) ?? forced.has(id);
  const tree = useMemo(() => (regions ? buildTree(regions) : []), [regions]);
  const countryOf = useMemo(() => {
    const byId = new Map((regions?.features ?? []).map((r) => [r.properties.id, r]));
    return (id: string) => {
      let cur = byId.get(id);
      while (cur?.properties.parent) cur = byId.get(cur.properties.parent);
      return cur?.properties.level === "country" ? cur.properties.id : null;
    };
  }, [regions]);
  const q = query.trim().toLocaleLowerCase();
  const matches = !regions || q.length < 2 ? null : regions.features
    .filter((r) => name(r).toLocaleLowerCase().includes(q) || r.properties.id.toLowerCase().includes(q))
    .sort((a, b) => collator.compare(name(a), name(b)))
    .slice(0, 30);

  const row = (r: RegionFeature, depth: number, hasChildren: boolean) => {
    const id = r.properties.id;
    const country = r.properties.level === "country" ? id : matches ? countryOf(id) : null;
    return (
      <div className="ow-tree__row" style={{ paddingInlineStart: depth * 14 }}>
        {hasChildren ? (
          <button type="button" className="ow-tree__toggle" aria-expanded={isOpen(id)}
            aria-label={t(isOpen(id) ? "area.collapse" : "area.expand", { name: name(r) })}
            onClick={() => setToggled((m) => new Map(m).set(id, !isOpen(id)))}>
            <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M4.5 3 7.5 6 4.5 9" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
          </button>
        ) : (
          <span className="ow-tree__toggle" aria-hidden="true" />
        )}
        <button type="button" className="ow-tree__item" aria-pressed={selectedId === id} onClick={() => onSelect(id)}>
          <span>{name(r)}</span>
          {country && <Flag country={country} />}
        </button>
      </div>
    );
  };

  const renderNodes = (nodes: Node[], depth: number) => (
    <ul className="ow-tree__list">
      {nodes.map((n) => (
        <li key={n.feature.properties.id}>
          {row(n.feature, depth, n.children.length > 0)}
          {n.children.length > 0 && isOpen(n.feature.properties.id) && renderNodes(n.children, depth + 1)}
        </li>
      ))}
    </ul>
  );

  return (
    <Tile title={t("area.title")} tour="area">
      <AreaPath path={path} onSelect={onSelect} />
      <button type="button" className="ow-tree__item ow-tree__item--all" aria-pressed={selectedId === null} onClick={() => onSelect(null)}>
        <span>{t("area.all")}</span>
        <span className="ow-flags"><Flag country="ES" /><Flag country="PT" /></span>
      </button>
      <label className="ow-search">
        <span className="visually-hidden">{t("area.search")}</span>
        <input type="search" className="ow-input" placeholder={t("area.search")} value={query} onChange={(e) => setQuery(e.target.value)} />
      </label>
      <div className="ow-tree">
        {!regions && <p className="ow-muted">{t("area.loading")}</p>}
        {matches
          ? matches.length
            ? <ul className="ow-tree__list">{matches.map((r) => <li key={r.properties.id}>{row(r, 0, false)}</li>)}</ul>
            : <p className="ow-muted">{t("area.none")}</p>
          : renderNodes(tree, 0)}
      </div>
    </Tile>
  );
}

// ------------------------------------------------------------------ fire-prone areas (collapsed by default)

const TOP_N = 8;

export function FrequentTile({ metric, conf, onPick }: { metric: "fires" | "frp_sum"; conf: ConfidenceLevel; onPick: (cell: string) => void }) {
  const { meta, finestRegions } = useAppData();
  const { t, f } = useI18n();
  const [open, setOpen] = useState(false);
  const q = useApiQuery(open ? `frequent|${meta.data_version}|${conf}` : null, (signal) =>
    fireApi.grid({ mode: "count", start: meta.first_date, end: meta.last_date, resolution: 5, min_confidence: conf }, signal),
  );
  const top = useMemo(() => {
    if (q.status !== "success" || !isGridCount(q.data)) return [];
    return [...q.data.cells].sort((a, b) => b[metric] - a[metric]).slice(0, TOP_N).map((c) => {
      const [lat, lon] = cellToLatLng(c.cell);
      return {
        ...c,
        name: regionAt([lon, lat], finestRegions)?.properties.name ?? null,
        position: `${f.one(Math.abs(lat))}° ${lat >= 0 ? "N" : "S"}, ${f.one(Math.abs(lon))}° ${lon >= 0 ? "E" : "W"}`,
      };
    });
  }, [q, metric, finestRegions, f]);

  return (
    <Tile title={t("freq.title")} defaultOpen={false}
      aside={<button type="button" className="ow-btn ow-btn--small" aria-expanded={open} onClick={() => setOpen((o) => !o)}>{t(open ? "freq.hide" : "freq.show")}</button>}>
      {!open && <p className="ow-muted ow-small">{t("freq.intro", { year: meta.first_date.slice(0, 4) })}</p>}
      {open && q.status === "loading" && <Loading label={t("freq.computing")} />}
      {open && q.status === "error" && <ErrorNote error={q.error} onRetry={q.reload} />}
      {open && top.length > 0 && (
        <ol className="ow-frequent">
          {top.map((c) => (
            <li key={c.cell}>
              <button type="button" className="ow-frequent__item" onClick={() => onPick(c.cell)}>
                <span className="ow-frequent__name">{c.name ?? t("freq.border")}</span>
                <span className="ow-muted ow-small">{c.position}</span>
                <span className="ow-frequent__value">{f.compact(c[metric])} {metric === "fires" ? t("unit.hotspots") : "MW"}</span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </Tile>
  );
}

// ------------------------------------------------------------------ drawing tools at the bottom of the map

const TOOLS: { mode: Exclude<DrawMode, "none">; icon: string }[] = [
  { mode: "rectangle", icon: "M3 5h14v10H3z" },
  { mode: "circle", icon: "M10 3a7 7 0 1 0 0.01 0z" },
  { mode: "polygon", icon: "M4 15 3 7l7-4 7 5-3 8z" },
  { mode: "freehand", icon: "M3 13c2-6 5 3 7-3s4 4 7-2" },
];

export function DrawBar({ mode, onMode, onClear, busy }: { mode: DrawMode; onMode: (m: DrawMode) => void; onClear: (() => void) | null; busy: boolean }) {
  const { t } = useI18n();
  return (
    <div className="ow-drawbar" data-tour="drawbar">
      {(mode !== "none" || busy) && (
        <p className="ow-drawbar__hint" aria-live="polite">
          {busy ? t("draw.registering") : `${t(`draw.${mode as Exclude<DrawMode, "none">}.hint`)} ${t("draw.esc")}`}
        </p>
      )}
      <div className="ow-drawbar__tools" role="toolbar" aria-label={t("draw.toolbar")}>
        <span className="ow-drawbar__label">{t("draw.label")}</span>
        {TOOLS.map((tool) => (
          <button key={tool.mode} type="button" className="ow-drawbar__btn" aria-pressed={mode === tool.mode} disabled={busy}
            onClick={() => onMode(mode === tool.mode ? "none" : tool.mode)}>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d={tool.icon} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /></svg>
            <span>{t(`draw.${tool.mode}`)}</span>
          </button>
        ))}
        {onClear && (
          <button type="button" className="ow-drawbar__btn ow-drawbar__btn--danger" onClick={onClear} disabled={busy}>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.6" /></svg>
            <span>{t("draw.clear")}</span>
          </button>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ info boxes over the map

export interface InfoBox {
  id: string;
  value: string;
  unit: string;
  label: string;
  note: string;
}

export function InfoBoxes({ boxes, visible }: { boxes: InfoBox[]; visible: boolean }) {
  return (
    <div className="ow-infoboxes" data-visible={visible} aria-hidden={!visible} aria-live="polite" data-tour="infoboxes">
      {boxes.map((b, i) => (
        <article key={b.id} className="ow-infobox" style={{ transitionDelay: visible ? `${i * 60}ms` : "0ms" }}>
          <p className="ow-infobox__label">{b.label}</p>
          <p className="ow-infobox__value">{b.value} <span className="ow-infobox__unit">{b.unit}</span></p>
          <p className="ow-infobox__note">{b.note}</p>
        </article>
      ))}
    </div>
  );
}
